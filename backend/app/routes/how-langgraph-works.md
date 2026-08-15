When you type "what is 2+2?" in the chat UI:
1. chat.py route receives the request (/api/chat/stream)
- Saves your message to the DB
- Packs the conversation into the initial graph state: {messages: [HumanMessage("what is 2+2?")], model: "unknown", pending_tool_calls: 0, pending_tool_calls_data: [], called_tools: []}
- Creates a fresh thread_id (UUID) so each conversation is isolated
- Starts streaming the graph via compiled_graph.astream_events(initial_state)
2. agent node runs
- Prepares messages: prepends SystemMessage (the "you are a helpful assistant" prompt)
- Calls llmconfig.router.stream() which resolves the user's saved LLM config
  (chat operation chain) and does an HTTP POST to that provider's
  OpenAI-compatible endpoint with stream: true
- The LLM streams back chunks (SSE events). Each chunk is an AIMessageChunk — either text tokens or tool call chunks
- The agent wraps each chunk as {"messages": [chunk], "pending_tool_calls": N} and yields it to LangGraph
- After streaming ends, accumulates partial tool_call_chunks into complete tool call data and yields pending_tool_calls_data
3. The LLM decides to call calculator(expression="2+2")
- The router's stream yields chunks with tool_call_chunks (falling back to the
  next alias in the config on rate_limit/server_error)
- The agent accumulates name, args, and id across chunks (grouped by index)
- After all chunks, yields {pending_tool_calls: 1, pending_tool_calls_data: [{name: "calculator", args: {expression: "2+2"}}]}
4. route_after_agent checks the switch
- Checks pending_tool_calls_data against called_tools set for repeats
- If all pending calls are repeats → routes to END (prevents infinite loops)
- If new calls detected → routes to tool_executor
5. tool_executor runs the real calculator
- Gets tool call data from pending_tool_calls_data (bypassing add_messages corruption)
- Builds a fresh AIMessage with tool_calls and passes to ToolNode
- Returns ToolMessage with result, clears pending_tool_calls_data, adds signature to called_tools
6. agent runs again (now with the tool result)
- LLM sees the tool result and responds with text: "The answer is 4."
- No tool calls this time → pending_tool_calls = 0
7. route_after_agent sees 0 → END
- The graph stops. The response "The answer is 4." is streamed to the UI as token events

Dedup safety: The called_tools set tracks all (tool_name, serialized_args) signatures. The edge
function checks pending calls against this set. If the LLM keeps calling the same tool with the
same arguments, the edge routes directly to END, breaking any infinite loop.
