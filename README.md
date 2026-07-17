# rag-based-sla-agent
hi, in this repo i am creating a rag based application which answers over the complex Microsoft SLA Document, later will implement agent which search for the question over web using web crawling and web scraping itself, creating a common database in which multiple tables are extracted from the Microsoft SLA Document which agents can use
   
   
# 3 Steps Procedure : 

1) QnA over Microsoft SLA Document
2) AWS SLA's
3) Google SLA's

# Source Links:
1) https://www.microsoft.com/licensing/docs/view/Service-Level-Agreements-SLA-for-Online-Services?lang=1

2) https://aws.amazon.com/legal/service-level-agreements/

3) https://cloud.google.com/terms/sla?hl=en

  
    
 
 
# STEPS 

verify the models you already downloaded can load
A. Embedding model check
Run:

powershell
python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer(r'./models/embedding/bge-small-en-v1.5'); v=m.encode(['What is the service credit for Application Gateway?']); print(v.shape)"

Expected
You should see something like:

powershell
(1, 384)
If this works, your embedding model is ready.




B. Reranker check
Run:

powershell
python -c "from sentence_transformers import CrossEncoder; m=CrossEncoder(r'./models/cross-encoder/ms-marco-MiniLM-L6-v2'); s=m.predict([['What is the service credit for Application Gateway?','Application Gateway service credit applies when uptime percentage falls below thresholds.']]); print(s)"
Expected
You should see a score array printed.

If yes, reranker is ready.



Step 3: verify FAISS works
Run:

powershell
python -c "import faiss, numpy as np; x=np.random.rand(10,384).astype('float32'); faiss.normalize_L2(x); idx=faiss.IndexFlatIP(384); idx.add(x); D,I=idx.search(x[:1],3); print('D=',D); print('I=',I)"
Expected
It should print distances and indices.

If yes, semantic vector retrieval is ready.

EG: 
D= [[1.         0.78991354 0.77279437]]
I= [[0 8 6]]




Step 4: verify SQLite FTS5 works
Run:

powershell
python -c "import sqlite3; con=sqlite3.connect(':memory:'); cur=con.cursor(); cur.execute('create virtual table t using fts5(text)'); cur.execute('insert into t(text) values (?)', ('Service Credit for Application Gateway',)); print(cur.execute(\"select rowid, text from t where t match 'Application'\").fetchall())"
Expected
You should see something like:

powershell
[(1, 'Service Credit for Application Gateway')]


<img width="649" height="462" alt="image" src="https://github.com/user-attachments/assets/f98b5c54-b956-4dfa-9fbe-335e2d7d000a" />




# Data Ingestion Flow
<img width="1154" height="320" alt="image" src="https://github.com/user-attachments/assets/c7f5a926-da14-4447-aefe-a359c1b64bc1" />



# RAG PIPELINE
<img width="951" height="657" alt="image" src="https://github.com/user-attachments/assets/1de03dd5-1249-49d7-9d8f-dedbe25649ac" />












