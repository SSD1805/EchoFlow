# EchoFlow

---

## **What is EchoFlow?**

**EchoFlow** is a local-first Python application foundation for audio processing. It is intended to handle tasks like **transcribing** and **analyzing** audio without requiring users to upload private, potentially large recordings to a hosted service.

EchoFlow is still under development. The repository currently contains its configuration, structured logging, local file-management, health-check, and performance-tracking foundation. Audio ingestion and transcription are roadmap work, not implemented features.

---

## 🌟 **Key Features**

1. **Scalable and Modular Architecture**
   - Adheres to **SOLID** and **DRY** principles for clean, maintainable design.
   - Centralized dependency management using `Dependency Injector`.
   - Core **Pipeline Manager** coordinates modular pipelines with clear separation of concerns.

2. **Utility-Driven Foundation**
   - Extensible **utilities** for file operations, datetime handling, and configuration management.
   - YAML utilities for configuration parsing and validation.
   - Security-focused utilities (in progress) for credential management and encryption.

3. **Planned Pipeline Management**
   - **Four planned pipelines**:
     - **Download Pipeline**: Handles downloads of video and audio files.
     - **Audio Pipeline**: Preprocesses and enhances audio files.
     - **Text Pipeline**: Refines and analyzes transcriptions.
     - **Transcription Pipeline**: Converts audio to text using tools like `OpenAI Whisper`.
   - A pipeline manager will orchestrate their interaction and execution.

4. **Enhanced Observability**
   - Container-managed **Logger** using `structlog` for structured diagnostics.
   - **Performance Tracker** to log system metrics and identify bottlenecks.
   - Health checks to monitor the operational status of critical components.

5. **Future-Proof Design**
   - Configurable using `.env` and environment variables for local deployments.

---

## 🛠️ **What's Been Built So Far**

### **1. Foundational Components**
- Modular structure ensures flexibility and easy integration of future features.
- Core utilities implemented, including:
  - **FileManagerFacade**: Handles file operations like saving, deleting, copying, and listing files.
  - **DateTimeUtility**: Offers robust timestamp handling, formatting, parsing, and elapsed time calculations.
  - **YAMLUtility**: Simplifies YAML parsing, validation, and writing with extensible features.

### **2. Core Modules**
- **Logger**: Container-managed structured logging with one configuration boundary.
- **Performance Tracker**: Tracks execution times for key operations, aiding in performance optimization.
- **HealthCheck Module**: Monitors the health of application components and reports issues early.

### **3. Utilities**
- **File Utilities**: Provide safe file operations, metadata retrieval, and sanitization.
- **Datetime Utilities**: Facilitate robust time and date operations with features like ISO 8601 formatting and elapsed time calculations.
- **YAML Utilities**: Streamline YAML operations with Pydantic-based validation and hooks for future features.

### **4. Testing Framework**
- Organized, nested test directories aligned with the application structure.
- Unit and integration tests using `pytest`, Factory Boy, and Hypothesis.
- Poodle mutation testing for the local foundation's observable behavior.

---

## 🛠️ **Technology Stack**

| **Category**               | **Tools/Frameworks**                           |
|----------------------------|-----------------------------------------------|
| **Language**               | Python 3.12                                   |
| **Interface**              | Local CLI; desktop interface planned          |
| **Dependency Management**  | uv                                            |
| **Configuration**          | Pydantic, .env                                |
| **Logging**                | structlog                                     |
| **Testing**                | pytest, Factory Boy, Hypothesis, Poodle      |
| **Audio Processing**       | Whisper-family transcription (planned)       |

---

## 🛠️ **Installation**

1. Clone the repository:
   ```bash
   git clone https://github.com/SSD1805/EchoFlow.git
   cd EchoFlow
   ```

2. Set up the virtual environment:
   ```bash
   uv sync
   ```

3. Create a `.env` file for configurations:
   ```bash
   echo "APP_ENV=development" >> .env
   echo "DEBUG=True" >> .env
   ```

4. Run the tests to ensure everything is set up correctly:
   ```bash
   uv run pytest
   ```

5. Run mutation tests for the foundation:
   ```bash
   uv run poodle
   ```

6. Inspect local requirements and optional tools:
   ```bash
   uv run echoflow doctor
   uv run echoflow doctor --json
   ```

`doctor` reports the workspace, disk space, FFmpeg, and system-resource state. A
required failure exits with status 1. Optional warnings exit successfully unless
`--strict` is supplied. Running `echoflow` without a subcommand only displays help;
it does not create files or run diagnostics.

---

## 🎯 **Roadmap**

- **Phase 1: Utility and Core Enhancements** (In Progress)
  - Enhance YAML utilities with schema validation and security hooks.
  - Build security utilities for credential encryption, masking, and safe storage.

- **Phase 2: Local CLI and Transcription**
  - Establish the `echoflow` CLI as the canonical interface.
  - Implement one local Whisper-family transcription path end to end.
  - Add the **Audio**, **Text**, and optional **Download** pipelines after that vertical slice works.
  - Finalize the **Pipeline Manager** for orchestrating pipeline workflows.

- **Phase 3: Observability and Security**
  - Add advanced performance monitoring and resource throttling utilities.
  - Integrate security measures like robust encryption and credential handling.

- **Phase 4: Desktop Interface**
  - Build a thin desktop interface over the same application layer used by the CLI.

- **Phase 5: Optional Scale-Out Execution**
  - Add background or distributed execution only when local workload evidence requires it.

- **Phase 6: Analytics and Visualization**
  - Add sentiment analysis and text analytics pipelines.
  - Create a dashboard for visualization of insights.

---

## 🙌 **Contributing**

We welcome contributions! If you'd like to collaborate:
1. Fork the repository.
2. Create a feature branch.
3. Submit a pull request with clear documentation.

---

## 📜 **License**

This project is licensed under the **Apache-2.0 License**. See the `LICENSE` file for more details.
```

