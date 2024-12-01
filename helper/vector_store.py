from langchain_milvus import Milvus
from langchain_openai import OpenAIEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.embeddings import QianfanEmbeddingsEndpoint
from langchain.schema import Document
from langchain_cohere import CohereEmbeddings
from typing import List, Optional
import os

class VectorStoreManager:
    def __init__(self, project: str, embedding_api_key: str, llm: str = "openai", **kwargs):
        """Initialize vector store manager
        
        Args:
            project: Project identifier used for collection name
            embedding_api_key: API key for embeddings
            llm: LLM type to determine which embeddings to use
            **kwargs: Additional configuration options for embeddings
                - model: Model name for embeddings (e.g., "text-embedding-3-small" for OpenAI)
                - qianfan_sk: Secret key for Qianfan embeddings
                - Other model-specific parameters
        """
        self.llm = llm
        
        # Get model name from kwargs or use default
        model = kwargs.get('model', {
            'openai': 'text-embedding-3-small',
            'zhipu': 'embedding-3',
            'cohere': 'embed-english-light-v3.0'
        }.get(llm))
        
        if llm == "gemini":
            self.embeddings = GoogleGenerativeAIEmbeddings(
                google_api_key=embedding_api_key,
                **kwargs
            )
        elif llm == "openai":
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=embedding_api_key,
                model=model,
                **kwargs
            )
        elif llm == "zhipu":
            self.embeddings = ZhipuAIEmbeddings(
                api_key=embedding_api_key,
                model=model,
                **kwargs
            )
        elif llm == "wenxin":
            self.embeddings = QianfanEmbeddingsEndpoint(
                qianfan_ak=embedding_api_key,
                qianfan_sk=kwargs.get('qianfan_sk'),
                **kwargs
            )
        elif llm == "cohere":
            self.embeddings = CohereEmbeddings(
                model=model,
                cohere_api_key=embedding_api_key,
                **kwargs
            )
        else:
            raise ValueError(f"Unsupported LLM type: {llm}")        
        # Set collection name
        self.collection_name = f"{project}"
        
        # Create data directory in project root
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(root_dir, "data", "vector_store")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Connection args for Milvus Lite
        self.connection_args = {
            "uri": f"{self.data_dir}/milvus_{self.llm}.db"
        }
        
    def create_vectorstore(self, documents: List[Document]) -> Milvus:
        """Create a new vector store from documents
        
        Args:
            documents: List of Document objects to store
        
        Returns:
            Milvus vector store instance
        """
        return Milvus.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            connection_args=self.connection_args
        )
    
    def get_vectorstore(self) -> Optional[Milvus]:
        """Get existing vector store
        
        Returns:
            Milvus vector store instance if exists, None otherwise
        """
        try:
            return Milvus(
                embedding_function=self.embeddings,
                collection_name=self.collection_name,
                connection_args=self.connection_args
            )
        except Exception:
            return None
            
    def similarity_search(self, query: str, k: int = 3, expr: str = None) -> List[Document]:
        """Search for similar documents
        
        Args:
            query: Search query string
            k: Number of results to return
            
        Returns:
            List of similar documents
        """
        vectorstore = self.get_vectorstore()
        if not vectorstore:
            return []
        res = vectorstore.max_marginal_relevance_search(query, k=k,fetch_k=10,lambda_mult=0.7, expr=expr)
        return res

    def add_documents(self, documents: List[Document]) -> bool:
        """Add multiple documents to the vector store
        
        Args:
            documents: List of Document objects to add
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            vectorstore = self.get_vectorstore()
            if vectorstore:
                # Add to existing vectorstore
                vectorstore.add_documents(documents)
            else:
                # Create new vectorstore if doesn't exist
                self.create_vectorstore(documents)
            return True
        except Exception as e:
            print(f"Error adding documents: {e}")
            return False
            
    def add_document(self, content: str, metadata: dict = None) -> bool:
        """Add a single document to the vector store
        
        Args:
            content: Text content of the document
            metadata: Optional metadata for the document
            
        Returns:
            bool: True if successful, False otherwise
        """
        doc = Document(
            page_content=content,
            metadata=metadata or {}
        )
        return self.add_documents([doc])
