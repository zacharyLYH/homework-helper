When you type "what is 2+2?" in the chat UI:
1. chat.py route receives the request (/api/chat/stream)
- Saves your message to the DB
- Packs the conversation into the initial graph state: {messages: [HumanMessage("what is 2+2?")], model: "unknown", pending_tool_calls: 0}
- Creates a fresh thread_id (UUID) so each conversation is isolated
- Starts streaming the graph via compiled_graph.astream_events(initial_state)
2. agent node runs
- Prepares messages: prepends SystemMessage (the "you are a helpful assistant" prompt)
- Calls stream_llm() which does an HTTP POST to OpenRouter/ChatOpenAI with stream: true
- The LLM streams back chunks (SSE events). Each chunk is an AIMessageChunk — either text tokens or tool call chunks
- The agent wraps each chunk as {"messages": [chunk], "pending_tool_calls": N} and yields it to LangGraph
3. The LLM decides to call calculator(expression="2+2")
- stream_llm yields chunks with tool_call_chunks like: [ToolCallChunk(name='calculator', args='{"expression":"2+2"}')]
- The agent detects these: checks hasattr(chunk, "tool_call_chunks"), looks for unique tool call IDs via seen_ids set, increments pending_tool_calls to 1
- Every subsequent yield includes "pending_tool_calls": 1
4. route_after_agent checks the switch
- Sees pending_tool_calls = 1 > 0 → routes to tool_executor
5. tool_executor runs the real calculator
- Picks up the last AIMessage (which has tool_calls = [{"name": "calculator", "args": {"expression": "2+2"}}])
- Calls ToolNode(ALL_TOOLS).invoke({"messages": [last_msg]})
- This runs the actual calculator Python function with expression = "2+2", returns "4"
- Yields {"messages": [ToolMessage(content="4")], "pending_tool_calls": 0} (decrements from 1)
6. agent runs again (now with the tool result)
- The conversation now includes: [HumanMessage("what is 2+2?"), AIMessage(tool_calls=...), ToolMessage(content="4")]
- LLM sees the tool result and responds with text: "The answer is 4."
- No tool calls this time → pending_tool_calls = 0
7. route_after_agent sees 0 → END
- The graph stops. The response "The answer is 4." is streamed to the UI as token events