"""
TODO: ChromaDB changes
1. Setup: Redis + ChromaDB server
2. Split vectorstore into 2 collections: context_data + chat_history
3. Add message caching to ChromaDB
4. Add TTL for old conversations

Essentially, the stream_bot_response function is currently loading the entire chat history into memory, which is not scalable. 
We need to implement a vectorstore that can store the chat history and retrieve it when needed.
"""

from langchain_openai import ChatOpenAI
import datetime
import os
from convo_backend.services.messages_cache import (
    cache_message,
    get_cached_messages,
)
from typing import AsyncGenerator
import logging
from convo_backend.services.dex_api import get_token_info
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langchain_community.document_loaders import TextLoader
from convo_backend.config import Config
from convo_backend.utils.latency import LatencyLog
from convo_backend.services.classifier import TextClassifier
import asyncio

latency_log = LatencyLog()


class ChatService:
    def __init__(self):
        """Initialize chat service with prompt templates, LLM configuration, and classifier."""
        self.logger = logging.getLogger("convo.chat")
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=os.environ["OPENAI_API_KEY"],
            streaming=True,
            max_tokens=1000,
        )
        self.tool_llm = ChatOpenAI(
            model="gpt-3.5-turbo-1106",
            api_key=os.environ["OPENAI_API_KEY"],
            streaming=False,
        )

        # Initialize prompt templates
        self.chat_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    TextLoader(Config.DEFAULT_PROMPT_PATH, encoding="utf-8")
                    .load()[0]
                    .page_content,
                ),
                # ("system", "You have access to the following external data to answer questions if they're asked: {data}"),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
            ]
        )

        self.space_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    TextLoader(Config.DEFAULT_PROMPT_PATH, encoding="utf-8")
                    .load()[0]
                    .page_content,
                ),
                (
                    "system",
                    TextLoader(Config.CHOOSE_SPACE_PROMPT_PATH, encoding="utf-8")
                    .load()[0]
                    .page_content,
                ),
            ]
        )

        self.filler_prompt = TextLoader(Config.FILLER_PROMPT_PATH, encoding="utf-8").load()[0].page_content

        # Initialize tools
        self.tools_dict = {"get_token_info": get_token_info}

        # Initialize classifier
        # self.text_classifier = TextClassifier()
        # self.logger.info("Text classifier initialized successfully.")


    async def stream_filler(self, current_message: str):
        formatted_prompt = self.filler_prompt.format(input=current_message)
        async for chunk in self.llm.astream(formatted_prompt):
            token = chunk.content
            self.logger.debug(f"Generated response token: {token}")
            yield token
    
    async def invoke_tools(self, tool_call_response):
        """Invokes all tool calls present in the langchain toolcall response"""
        tool_calls = tool_call_response.tool_calls
        aggregated_data = []

        if not tool_calls:
            return None
        for tool_call in tool_calls:
            if tool_call["name"] in self.tools_dict:
                result = await self.tools_dict[tool_call["name"]].arun(tool_call["args"])
                aggregated_data.append(
                    result
                )
        return aggregated_data
    
    async def query_tools(self, current_message : str):
        """Makes a call to openai to see what tools need to be called"""
        #bind tools to llm
        tool_call_chain = self.tool_llm.bind_tools(
            self.tools_dict.values()
        )
        return await tool_call_chain.ainvoke(
            current_message
        )
    
    async def get_api_data(self, current_message : str) -> list:
        """Makes query to openai for tools and then calls those tools, returning the aggregated data"""
        response = await self.query_tools(
            current_message
        )
        return await self.invoke_tools(
            response
        )
        
    @latency_log.track_latency(name="OpenAI <stream_bot_response>", stream=True)
    async def stream_bot_response(
        self,
        current_message: dict = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate and stream an AI response based on chat history and current message.

        Uses OpenAI's ChatGPT to generate responses, incorporating chat history and a
        system prompt. Responses are streamed token by token and cached after completion.

        Args:
            current_message (dict, optional): The latest user message to respond to

        Yields:
            str: Response tokens as they are generated (response text chunks)

        Raises:
            Exception: If there are errors during response generation or caching
        """
        try:
            # self.logger.info("Initiating new chat response")

            # # Classify the current message
            # classification_result = self.text_classifier.classify(current_message["message"])
            # self.logger.info(f"Classification result: {classification_result}")

            # # Optionally, modify behavior based on classification_result
            # # For example, you can adjust the prompt or take specific actions

            # Initialize response dict
            response_dict = {"message": "", "timeStamp": None, "sender": "bot"}

            #Check if api call is needed
            if False:
                #Start an async task to get additional data
                get_api_data_task = asyncio.create_task(
                    self.get_api_data(
                        current_message["message"]
                    )
                )
                # While that's going, stream a filler message
                async for token in self.stream_filler(current_message["message"]):
                     yield token

                #Await on the api data task to finish
                data = await get_api_data_task
            #If not, continue with normal response process
            else: 
                # Only need chat history if we are proceeding with normal response
                messages_list = await self.get_chat_history()
                chat_history = [
                    (
                        AIMessage(content=message_dict["message"])
                        if message_dict["sender"] == "bot"
                        else HumanMessage(content=message_dict["message"])
                    )
                    for message_dict in messages_list
                ]

                # Set time message was generated
                response_dict["timeStamp"] = datetime.datetime.now()

            # Create chain
            chain = self.chat_prompt | self.llm

            async for chunk in chain.astream(
                {
                    "input": current_message["message"],
                    "chat_history": chat_history # chat history not required if needing to give api based answer
                }
            ):
                token = chunk.content
                response_dict["message"] += token
                self.logger.debug(f"Generated response token: {token}")
                yield token

            self.logger.info("Chat response completed")
            await cache_message(response_dict)

        except Exception as e:
            self.logger.error(f"Error generating chat response: {e}", exc_info=True)

    async def choose_x_space(self, spaces: list[dict]):
        chain = self.space_prompt | self.llm
        response = await chain.ainvoke({"spaces": str(spaces)})
        return response.content

    async def mute_unmute_sensing_task(
        self, current_message: dict, toggle_mute_tool: StructuredTool
    ):
        """
        Sensing task to mute or unmute the bot based on voice command.
        """
        llm_with_tool = self.tool_llm.bind_tools([toggle_mute_tool])

        if (
            "mute" in current_message["message"].lower()
            or "unmute" in current_message["message"].lower()
        ):
            result = await llm_with_tool.ainvoke(current_message["message"])

            # Add debug logging
            print(f"Result type: {type(result.tool_calls)}")
            print(f"Result content: {result.tool_calls}")

            if result.tool_calls:
                tool_call = result.tool_calls[0]
                await toggle_mute_tool.arun(tool_call["args"])

    async def initialize_vectorstore(self):
        """
        Initialize the vector store for chat history and context data.

        TODO: Implement ChromaDB initialization and configuration
        """
        pass

    async def get_chat_history(self):
        """
        Retrieve the conversation history from cache.

        Returns:
            list[dict]: List of previous messages with their metadata
        """
        return await get_cached_messages()