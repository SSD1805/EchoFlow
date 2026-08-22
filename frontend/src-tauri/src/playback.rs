use crate::backend;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::fs::{File, Metadata};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::UNIX_EPOCH;
use tauri::http::{self, header};
use tauri::State;

const MAX_ACTIVE_SESSIONS: usize = 8;
const MAX_RANGE_BYTES: u64 = 1024 * 1024;

#[derive(Debug, Deserialize)]
pub struct PlaybackPrepareRequest {
    document_id: String,
    canonical_sha256: String,
    seek_seconds: f64,
}

#[derive(Debug, Serialize)]
pub struct PlaybackPrepared {
    session_id: String,
    media_token: String,
    duration_seconds: f64,
    seek_seconds: f64,
    media_kind: String,
}

#[derive(Debug, Serialize)]
pub struct PlaybackReleased {
    released: bool,
}

#[derive(Debug, Deserialize)]
struct BridgeError {
    message: String,
}

#[derive(Debug, Deserialize)]
struct TrustedGrant {
    source_path: String,
    source_size_bytes: u64,
    source_modified_ns: u64,
    duration_seconds: f64,
    seek_seconds: f64,
    media_kind: String,
}

#[derive(Debug, Deserialize)]
struct BridgeResponse {
    ok: bool,
    result: Option<TrustedGrant>,
    error: Option<BridgeError>,
}

struct PlaybackSession {
    file: Arc<File>,
    length: u64,
    content_type: &'static str,
}

#[derive(Clone, Default)]
pub struct PlaybackSessions {
    inner: Arc<Mutex<HashMap<String, PlaybackSession>>>,
    counter: Arc<AtomicU64>,
}

impl PlaybackSessions {
    fn insert(&self, session: PlaybackSession) -> Result<String, String> {
        let mut sessions = self
            .inner
            .lock()
            .map_err(|_| "Playback session state is unavailable".to_string())?;
        if sessions.len() >= MAX_ACTIVE_SESSIONS {
            return Err(
                "Too many playback sessions are open; close another evidence player and retry"
                    .to_string(),
            );
        }
        let id = self.counter.fetch_add(1, Ordering::Relaxed) + 1;
        let session_id = format!("p{id:016x}");
        sessions.insert(session_id.clone(), session);
        Ok(session_id)
    }

    fn remove(&self, session_id: &str) -> Result<bool, String> {
        if !valid_session_id(session_id) {
            return Ok(false);
        }
        self.inner
            .lock()
            .map(|mut sessions| sessions.remove(session_id).is_some())
            .map_err(|_| "Playback session state is unavailable".to_string())
    }

    fn session(&self, session_id: &str) -> Option<(Arc<File>, u64, &'static str)> {
        if !valid_session_id(session_id) {
            return None;
        }
        let sessions = self.inner.lock().ok()?;
        let session = sessions.get(session_id)?;
        Some((
            Arc::clone(&session.file),
            session.length,
            session.content_type,
        ))
    }

    pub fn protocol_response(&self, request: http::Request<Vec<u8>>) -> http::Response<Vec<u8>> {
        let method = request.method().clone();
        if method != http::Method::GET && method != http::Method::HEAD {
            return response_with_status(http::StatusCode::METHOD_NOT_ALLOWED);
        }
        let session_id = request.uri().path().trim_start_matches('/');
        let Some((file, length, content_type)) = self.session(session_id) else {
            return response_with_status(http::StatusCode::NOT_FOUND);
        };
        if length == 0 {
            return response_with_status(http::StatusCode::NOT_FOUND);
        }

        let mut builder = http::Response::builder()
            .header(header::CONTENT_TYPE, content_type)
            .header(header::ACCEPT_RANGES, "bytes")
            .header(header::CACHE_CONTROL, "no-store");

        if method == http::Method::HEAD {
            return builder
                .header(header::CONTENT_LENGTH, length)
                .status(http::StatusCode::OK)
                .body(Vec::new())
                .unwrap_or_else(|_| response_with_status(http::StatusCode::INTERNAL_SERVER_ERROR));
        }

        let requested = request
            .headers()
            .get(header::RANGE)
            .and_then(|value| value.to_str().ok());
        let range = match requested {
            Some(value) => match parse_single_range(value, length) {
                Some(range) => range,
                None => return range_not_satisfiable(length),
            },
            None if length > MAX_RANGE_BYTES => (0, MAX_RANGE_BYTES - 1),
            None => (0, length - 1),
        };
        let (start, requested_end) = range;
        let end = requested_end.min(start.saturating_add(MAX_RANGE_BYTES - 1));
        let bytes_to_read = end + 1 - start;

        let mut local_file = match file.try_clone() {
            Ok(file) => file,
            Err(_) => return response_with_status(http::StatusCode::INTERNAL_SERVER_ERROR),
        };
        if local_file.seek(SeekFrom::Start(start)).is_err() {
            return response_with_status(http::StatusCode::INTERNAL_SERVER_ERROR);
        }
        let mut body = Vec::with_capacity(bytes_to_read as usize);
        if local_file
            .take(bytes_to_read)
            .read_to_end(&mut body)
            .is_err()
        {
            return response_with_status(http::StatusCode::INTERNAL_SERVER_ERROR);
        }

        let partial = requested.is_some() || start != 0 || end + 1 != length;
        if partial {
            builder = builder.status(http::StatusCode::PARTIAL_CONTENT).header(
                header::CONTENT_RANGE,
                format!("bytes {start}-{end}/{length}"),
            );
        } else {
            builder = builder.status(http::StatusCode::OK);
        }
        builder
            .header(header::CONTENT_LENGTH, body.len())
            .body(body)
            .unwrap_or_else(|_| response_with_status(http::StatusCode::INTERNAL_SERVER_ERROR))
    }
}

fn response_with_status(status: http::StatusCode) -> http::Response<Vec<u8>> {
    http::Response::builder()
        .status(status)
        .header(header::CACHE_CONTROL, "no-store")
        .body(Vec::new())
        .unwrap_or_else(|_| http::Response::new(Vec::new()))
}

fn range_not_satisfiable(length: u64) -> http::Response<Vec<u8>> {
    http::Response::builder()
        .status(http::StatusCode::RANGE_NOT_SATISFIABLE)
        .header(header::CONTENT_RANGE, format!("bytes */{length}"))
        .header(header::CACHE_CONTROL, "no-store")
        .body(Vec::new())
        .unwrap_or_else(|_| response_with_status(http::StatusCode::RANGE_NOT_SATISFIABLE))
}

fn valid_session_id(value: &str) -> bool {
    value.len() == 17
        && value.starts_with('p')
        && value[1..].bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn parse_single_range(value: &str, length: u64) -> Option<(u64, u64)> {
    let value = value.strip_prefix("bytes=")?;
    if value.contains(',') || length == 0 {
        return None;
    }
    let (start_text, end_text) = value.split_once('-')?;
    if start_text.is_empty() {
        let suffix = end_text.parse::<u64>().ok()?;
        if suffix == 0 {
            return None;
        }
        let start = length.saturating_sub(suffix.min(length));
        return Some((start, length - 1));
    }

    let start = start_text.parse::<u64>().ok()?;
    if start >= length {
        return None;
    }
    let end = if end_text.is_empty() {
        length - 1
    } else {
        end_text.parse::<u64>().ok()?.min(length - 1)
    };
    if end < start {
        return None;
    }
    Some((start, end))
}

fn modified_ns(metadata: &Metadata) -> Option<u128> {
    metadata
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|duration| duration.as_nanos())
}

fn content_type(path: &Path, media_kind: &str) -> &'static str {
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    match extension.as_str() {
        "aac" => "audio/aac",
        "aiff" => "audio/aiff",
        "flac" => "audio/flac",
        "m4a" => "audio/mp4",
        "mp3" => "audio/mpeg",
        "ogg" | "opus" => "audio/ogg",
        "wav" => "audio/wav",
        "wma" => "audio/x-ms-wma",
        "avi" => "video/x-msvideo",
        "m4v" | "mp4" if media_kind == "video" => "video/mp4",
        "m4v" | "mp4" => "audio/mp4",
        "mkv" => "video/x-matroska",
        "mov" => "video/quicktime",
        "mpeg" | "mpg" => "video/mpeg",
        "webm" if media_kind == "video" => "video/webm",
        "webm" => "audio/webm",
        _ => "application/octet-stream",
    }
}

fn bridge_error(response: &BridgeResponse) -> String {
    response
        .error
        .as_ref()
        .map(|error| error.message.clone())
        .unwrap_or_else(|| "EchoFlow could not authorize local playback".to_string())
}

#[tauri::command]
pub async fn playback_prepare(
    request: PlaybackPrepareRequest,
    sessions: State<'_, PlaybackSessions>,
) -> Result<PlaybackPrepared, String> {
    let payload = json!({
        "protocol_version": 1,
        "request_id": "native-playback",
        "method": "playback.authorize",
        "params": {
            "document_id": request.document_id,
            "canonical_sha256": request.canonical_sha256,
            "seek_seconds": request.seek_seconds,
        }
    });
    let raw = backend::playback_authorization_request(payload).await?;
    let response: BridgeResponse = serde_json::from_value(raw)
        .map_err(|_| "EchoFlow's playback authorization response was invalid".to_string())?;
    if !response.ok {
        return Err(bridge_error(&response));
    }
    let grant = response
        .result
        .ok_or_else(|| "EchoFlow's playback authorization response was incomplete".to_string())?;
    if !grant.duration_seconds.is_finite()
        || !grant.seek_seconds.is_finite()
        || grant.seek_seconds < 0.0
        || grant.seek_seconds > grant.duration_seconds
        || !matches!(grant.media_kind.as_str(), "audio" | "video")
    {
        return Err("EchoFlow's playback authorization response was invalid".to_string());
    }

    let source_path = PathBuf::from(&grant.source_path);
    let file = File::open(&source_path)
        .map_err(|_| "The verified recording could not be opened for local playback".to_string())?;
    let metadata = file.metadata().map_err(|_| {
        "The verified recording could not be inspected for local playback".to_string()
    })?;
    if metadata.len() != grant.source_size_bytes
        || modified_ns(&metadata) != Some(u128::from(grant.source_modified_ns))
    {
        return Err(
            "The recording changed between verification and native playback; retry from the evidence view"
                .to_string(),
        );
    }

    let kind = grant.media_kind.clone();
    let session_id = sessions.insert(PlaybackSession {
        file: Arc::new(file),
        length: metadata.len(),
        content_type: content_type(&source_path, &kind),
    })?;
    Ok(PlaybackPrepared {
        media_token: session_id.clone(),
        session_id,
        duration_seconds: grant.duration_seconds,
        seek_seconds: grant.seek_seconds,
        media_kind: kind,
    })
}

#[tauri::command]
pub fn playback_release(
    session_id: String,
    sessions: State<'_, PlaybackSessions>,
) -> Result<PlaybackReleased, String> {
    Ok(PlaybackReleased {
        released: sessions.remove(&session_id)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn range_parser_accepts_bounded_open_and_suffix_ranges() {
        assert_eq!(parse_single_range("bytes=0-99", 1_000), Some((0, 99)));
        assert_eq!(parse_single_range("bytes=900-", 1_000), Some((900, 999)));
        assert_eq!(parse_single_range("bytes=-100", 1_000), Some((900, 999)));
        assert_eq!(
            parse_single_range("bytes=100-9999", 1_000),
            Some((100, 999))
        );
    }

    #[test]
    fn range_parser_rejects_multipart_and_invalid_bounds() {
        assert_eq!(parse_single_range("bytes=0-1,4-5", 100), None);
        assert_eq!(parse_single_range("bytes=100-", 100), None);
        assert_eq!(parse_single_range("bytes=9-3", 100), None);
        assert_eq!(parse_single_range("items=0-3", 100), None);
        assert_eq!(parse_single_range("bytes=-0", 100), None);
    }

    #[test]
    fn session_ids_are_closed_tokens_not_paths() {
        assert!(valid_session_id("p0000000000000001"));
        assert!(!valid_session_id("../secret.mp4"));
        assert!(!valid_session_id("p000000000000000g"));
    }

    #[test]
    fn protocol_caps_large_reads_and_rejects_unknown_tokens() {
        let temp = std::env::temp_dir().join(format!(
            "echoflow-playback-test-{}-{}",
            std::process::id(),
            1
        ));
        let mut file = File::create(&temp).expect("create temp media");
        file.write_all(&vec![7_u8; (MAX_RANGE_BYTES + 64) as usize])
            .expect("write temp media");
        drop(file);
        let source = File::open(&temp).expect("open temp media");
        let sessions = PlaybackSessions::default();
        let token = sessions
            .insert(PlaybackSession {
                file: Arc::new(source),
                length: MAX_RANGE_BYTES + 64,
                content_type: "audio/wav",
            })
            .expect("insert session");

        let request = http::Request::builder()
            .method(http::Method::GET)
            .uri(format!("http://echoflow-media.localhost/{token}"))
            .body(Vec::new())
            .expect("build request");
        let response = sessions.protocol_response(request);
        assert_eq!(response.status(), http::StatusCode::PARTIAL_CONTENT);
        assert_eq!(response.body().len(), MAX_RANGE_BYTES as usize);

        let missing = http::Request::builder()
            .method(http::Method::GET)
            .uri("http://echoflow-media.localhost/p00000000000000ff")
            .body(Vec::new())
            .expect("build missing request");
        assert_eq!(
            sessions.protocol_response(missing).status(),
            http::StatusCode::NOT_FOUND
        );
        let _ = std::fs::remove_file(temp);
    }
}
