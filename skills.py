import re

ALIASES = {
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "ml": "machine learning",
    "dl": "deep learning",
    "tf": "tensorflow",
    "js": "javascript",
    "py": "python",
    "postgres": "postgresql",
    "llms": "llm",
    "large language models": "llm",
    "large language model": "llm",
    "retrieval augmented generation": "rag",
    "retrieval-augmented generation": "rag",
    "gen ai": "generative ai",
    "genai": "generative ai",
    "amazon web services": "aws",
    "hugging face": "huggingface",
    "power bi": "powerbi",
    "databases": "database",
    "vector db": "vector database",
    "vector dbs": "vector database",
    "vector databases": "vector database",
}

# a general term in a job description is satisfied by any specific tool in its group
CONCEPTS = {
    "database": {"mysql", "postgresql", "sqlite", "mongodb", "sql", "oracle", "redis"},
    "sql": {"sql", "mysql", "postgresql", "sqlite"},
    "vector database": {"pinecone", "chroma", "chromadb", "faiss", "qdrant",
                        "weaviate", "milvus", "pgvector"},
    "containerization": {"docker", "kubernetes"},
    "data science libraries": {"pandas", "numpy", "scikit-learn", "matplotlib", "scipy"},
    "cloud": {"aws", "azure", "gcp", "oracle cloud"},
    "version control": {"git", "github"},
    "data visualization": {"matplotlib", "powerbi", "tableau", "seaborn"},
}

# NOT used for scoring. When a required skill is missing, terms found in the resume that
# are related to it are shown as "related evidence" so the user can see the gap and the
# nearby proof side by side. The skill itself is never counted as matched because of these.
RELATED = {
    "machine learning": {"scikit-learn", "classification", "regression", "random forest",
                         "logistic regression", "knn", "decision tree", "neural network",
                         "clustering", "xgboost", "model training", "predictive model"},
    "deep learning": {"tensorflow", "pytorch", "keras", "neural network", "cnn", "lstm"},
    "nlp": {"nltk", "spacy", "text classification", "sentiment analysis",
            "sentence transformers", "huggingface"},
    "generative ai": {"llm", "rag", "prompt engineering", "groq api", "ollama"},
    "data analysis": {"pandas", "numpy", "data cleaning", "eda", "matplotlib", "seaborn"},
}


def normalize(skill: str) -> str:
    s = skill.lower().strip()
    s = re.sub(r"[^a-z0-9+#.\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)