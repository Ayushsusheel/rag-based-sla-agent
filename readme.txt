1) activate venv

PS C:\Users\susheela\Downloads\rag_sla_fullyOffline> 

& "c:/Users/susheela/Downloads/IRIS - ST1518/__Code__/ST_DataBuddy_for_13_MAY_2026_implementingTalk2DB/.venv/Scripts/Activate.ps1"     





<!-- R U N    THIS    S I N G L E     COMMAND ONLY  -->
2) run everything in single command : 

python -m streamlit run main.py --server.fileWatcherType none






3) FIX PIP INSTALL
Step 1: download the two correct wheels on this same machine
Run this exact command:

powershell
python -m pip download --use-feature=truststore --only-binary=:all: -d wheelhouse huggingface-hub==1.14.0 tokenizers==0.22.2
If that succeeds, you’ll have the wheels in .\wheelhouse.

Step 2: install them offline and force them back
Run this exact command:

powershell
python -m pip install --no-index --find-links=".\wheelhouse" --no-deps --force-reinstall huggingface-hub==1.14.0 tokenizers==0.22.2


then verify :
python -c "import chromadb; print('CHROMA_OK', chromadb.__version__)"


Step 3: verify everything
Run these commands exactly.

Verify versions
powershell
python -c "import chromadb, transformers, huggingface_hub, tokenizers; print('CHROMA', chromadb.__version__); print('TRANSFORMERS', transformers.__version__); print('HF_HUB', huggingface_hub.__version__); print('TOKENIZERS', tokenizers.__version__)"



