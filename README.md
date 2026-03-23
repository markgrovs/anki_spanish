# Spanish Anki Deck Builder

A set of Python tools to build, manage, and enrich a Spanish Anki deck based on the Fluent Forever 625-word list. It automates fetching vocabulary metadata (IPA, Part of Speech, Gender), picking images, generating audio, and pushing the final cards directly to Anki.

## Prerequisites

Before setting up the Python environment, ensure you have the following installed:
*   [Python](https://www.python.org/downloads/) 3.10 or higher.
*   [Anki](https://apps.ankiweb.net/) desktop application running in the background.
*   [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed in Anki (Add-on code: `2055492159`) to allow the scripts to communicate with your local Anki database.

---

## Python Environment Setup

It is highly recommended to run this project inside an isolated virtual environment. Follow these steps to get everything configured:

### 1. Navigate to the project directory
Open your terminal and navigate to the project folder:
```bash
cd "/Users/markgroves/Documents/[06] Development/spanish_anki"
```

### 2. Create a virtual environment
Create a new virtual environment. We'll use `.venv312` as the directory name.
```bash
python3 -m venv .venv312
```

### 3. Activate the virtual environment
You must activate the virtual environment every time you open a new terminal session to work on this project.
*   **macOS / Linux:**
    ```bash
    source .venv312/bin/activate
    ```
*   **Windows:**
    ```cmd
    .venv312\Scripts\activate
    ```
*(You will know it is active when your terminal prompt is prefixed with `(.venv312)`).*

### 4. Install dependencies
The project dependencies are managed via `pyproject.toml`. Install the base package requirements (Requests, Pillow, PyYAML) in editable mode:
```bash
pip install -e .
```

#### Optional Dependencies
Depending on which parts of the workflow you are using, you may need to install optional dependency groups:

*   **Translation Tools** (Installs `argostranslate` and `deep-translator`):
    ```bash
    pip install -e ".[translate]"
    ```
*   **Text-to-Speech / IPA Tools** (Installs `phonemizer` and `epitran`):
    ```bash
    pip install -e ".[tts]"
    ```
*   **Development Tools** (Installs `pytest`, `black`, and `mypy` for code formatting and testing):
    ```bash
    pip install -e ".[dev]"
    ```
*   **Install All Dependencies at Once:**
    ```bash
    pip install -e ".[translate,tts,dev]"
    ```

### 5. Environment Variables
There is a `.env` file present in the directory. Ensure it contains any required API keys (e.g., Pixabay for image fetching) or necessary configuration variables.

---

## Usage

Once your environment is set up and activated, you manage the entire project through the unified command-line interface: `anki_flow.py`.

> **Note:** Make sure the Anki desktop application is open before running commands that interact with the deck (like `build` or `sync`).

To see all available commands, run:
```bash
python3 anki_flow.py --help
```

### Core Commands Overview:
*   `python3 anki_flow.py pick` - Interactive Spanish selection
*   `python3 anki_flow.py enrich-all` - Automatically fill missing POS, Gender, and IPA data
*   `python3 anki_flow.py pick-images` - Interactive image picker (Pixabay)
*   `python3 anki_flow.py build` - Build or update the cards in Anki
*   `python3 anki_flow.py audit` - Report missing translations or assets
