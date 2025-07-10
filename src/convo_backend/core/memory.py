from langchain_core.vectorstores import InMemoryVectorStore
import convo_backend.models.memory as memory
from mongoengine import QuerySet
from datetime import datetime
from langchain_openai import OpenAIEmbeddings
import os
from httpx import AsyncClient
from sentence_transformers import SentenceTransformer
import mongoengine as me
from convo_backend.config import Config
from datetime import datetime, timedelta
import json


class Memory:
    """
    Singleton class for managing memory operations.
    """

    _instance = None

    def __new__(cls):
        """
        Singleton class for managing memory operations. Only one instance of Memory is created.
        """
        if cls._instance is None:
            cls._instance = super(Memory, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the memory with short-term and long-term storage, as well as embedding models.
        """

        # Connect mongodb
        me.connect(host=os.getenv("MONGO_URI"), db="Convo")

        self.high_dim_embedding_model = OpenAIEmbeddings(
            async_client=AsyncClient,
            api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-ada-002",
        )
        self.low_dim_embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.short_term_memory = InMemoryVectorStore(
            embedding=self.low_dim_embedding_model.encode
        )
        self.long_term_memory = memory

    def get_short_term_memory(self) -> InMemoryVectorStore:
        """
        Returns the short-term memory instance.
        """
        return self.short_term_memory

    def get_long_term_memory(self) -> QuerySet:
        """
        Returns a QuerySet of all long-term memories.
        """
        return self.long_term_memory.Memory.objects()

    def save_to_short_term_memory(self, data: str):
        """
        Saves data to the short-term memory.
        """
        self.short_term_memory.add_texts([data])

    def save_to_long_term_memory(self, data: str, created_at: datetime.now = None):
        """
        Saves data to the long-term memory with embeddings.
        """
        high_dim = self.high_dim_embedding_model.embed_query(data)
        low_dim = self.low_dim_embedding_model.encode(data).tolist()
        new_memory = self.long_term_memory.Memory(
            text=data,
            created_at=created_at if created_at else datetime.now(),
            high_dim_embedding=high_dim,
            low_dim_embedding=low_dim,
        )
        new_memory.save()

    def retrieve_from_short_term_memory(self, query):
        """
        Retrieves data from the short-term memory based on a query.
        """
        embedding = self.low_dim_embedding_model.encode(query)
        return self.short_term_memory.similarity_search_by_vector(embedding=embedding)

    def retrieve_from_long_term_memory(self, query):
        """
        Placeholder for future implementation of long-term memory retrieval.
        """
        pass

    def save_chat_session(self, chat_group_id: str):
        """
        Save the chat group id
        """
        data_file = f"{Config.DATA_SAVE_PATH}/chat_group_id.json"
        
        if not os.path.exists(Config.DATA_SAVE_PATH):
            os.makedirs(Config.DATA_SAVE_PATH)
        with open(data_file, "w+") as f:
            # if the time from when the session was created exceeds 1 days or there is no data, save the new session data
            if os.path.getsize(data_file) == 0 or datetime.now() - json.loads(
                f.read(data_file)
            )["created"] > timedelta(days=1):
                f.write(
                    json.dumps(
                        {
                            "chat_group_id": chat_group_id,
                            "created": datetime.now().isoformat(),
                        }
                    )
                )

    def get_chat_session(self) -> dict:
        data_file = f"{Config.DATA_SAVE_PATH}/chat_group_id.json"
        if not os.path.exists(data_file):
            return None

        with open(data_file, "r") as f:
            data = json.loads(f.read())
            data["created"] = datetime.fromisoformat(data["created"])
            return data
