GENERATE_QUERY = """
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct {dialect} query to run,
then look at the results of the query and return the answer. Unless the user
specifies a specific number of examples they wish to obtain, always limit your
query to at most {top_k} results if not specified by the user.

[Schema of Candiate Tables]
{schema_for_candidate_tables}

You can order the results by a relevant column to return the most interesting
examples in the database. Never query for all the columns from a specific table,
only ask for the relevant columns given the question.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.

Use these additional context channels when relevant:

[INSTRUCTION CONTEXT]
{instruction_context}

[QUERY MEMORY]
{query_memory_context}

If context channels conflict, prioritize schema facts, then instruction context, then query memory examples.

Double check your query for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins

IMPORTANT: Return ONLY the tool call. Do not output any explanation before or after the tool call. Ensure the SQL query is properly escaped.
"""

ANALYZE_RESULT = """
You are a Data Analyst. Evaluate the SQL execution result against the user request.

USER REQUEST: {user_input}
SQL QUERY EXECUTED: {query_executed}
DATABASE RESPONSE: {database_output}
CURRENT RETRY ATTEMPT: {retry_count}
USER INSTRUCTIONS: {instruction_context}

EVALUATION RULES:
1. SUCCESS: Data directly answers the question.
2. ERROR: Database returned a syntax or execution error.
3. IRRELEVANT: Data returned does not match the semantic intent of the question.
4. EMPTY_RESULT: Query executed successfully but returned 0 rows.

INSTRUCTIONS:
- If SUCCESS: Explain why the query correctly answers the question.
- If ERROR: Explain the technical error and add the error in the explanation.
- If IRRELEVANT: Explain which columns/data were wrong.
- If EMPTY_RESULT: 
  - If retry_count is 0: Suggest broader filters (e.g. remove WHERE clause, use LIKE).
  - If retry_count > 0:  State confidently that no data exists for this request.

OUTPUT FORMAT:
Return valid JSON matching the AnalysisResult schema.

IMPORTANT: If the database respone is close enough to anwer the question you can mark it as SUCCESS, but mention in the explanation what is missing or not fully aligned with the user's intent.
"""

EXPLAIN_RESULT = """
You are a helpful data assistant presenting query results to a non-technical user.
Based on the outcome of the SQL query execution, respond appropriately using one of the cases below.

User question: {user_question}

SQL executed:
{query}

Status: {status}

Result:
{database_output}

Analysis:
{explanation}

---

Follow these instructions based on the status:

- success: Present the results clearly and concisely in natural language. Summarize key findings, highlight important values, and format tables or lists if needed.

- empty_result: Inform the user that the query ran successfully but returned no matching data. Suggest that the data they are looking for may not exist in the database, or that their question may need to be rephrased.

- irrelevant: Show the returned data to the user and explain that while the query executed, the results may not fully match their intent. Ask the user if this is close to what they were looking for or if they would like to refine the question.

- error: Apologize and inform the user that the query could not be executed due to an internal error after multiple attempts. Avoid technical jargon. Suggest they rephrase their question or contact support.

Always be concise, friendly, and avoid exposing raw SQL or technical error messages to the user.
"""


REGENERATE_QUERY_ON_ERROR = """
The previous query produced an error.

SQL:
{query}

Error:
{explanation}

Fix the SQL query. Do not repeat the same mistake.

Here is more context that might be helpful.

Preivous failed queries : {previous_queries}
"""

REGENERATE_QUERY_ON_EMPTY_RESULT = """
The previous query executed successfully but returned no results.

SQL:{query}

Analysis:{explanation}

Reconsider your assumptions — the filters, joins, or conditions may be too restrictive. 
Generate a revised query that is more likely to return data.

Here is more context that might be helpful.

Preivous failed queries : {previous_queries}
"""

HANDLE_IRRELEVANT_RESULT = """
The query executed successfully and returned data, but the results do not match the semantic intent of the user's question.

User question: {user_question}

Available tables: {available_tables}

Previous Candidate tables: {candidate_tables}

Schema context: {schema_context}

Instruction Context : {instruction_context}

SQL executed:
{query}

Data returned:
{database_output}

Analysis:
{explanation}

This likely means the query is targeting the wrong table, column, or relationship.
Identify the correct tables and columns that semantically match the user's question.
Do not reuse the previous query logic — approach the schema with fresh eyes.
"""

SHOULD_SKIP = """
You are given a list of tables available in a SQL database: {available_tables}
Decide if the user's question can possibly be answered using these tables.
User question: {user_question}

- If the question refers to entities, roles, or data that clearly do not exist in any of these tables, set skip=true and explain why in plain language.
- If there is any reasonable chance the question can be answered, set skip=false.
- Do NOT skip just because results might be empty ,only skip when the schema fundamentally lacks the required data.

Additional Context : {schema_context}
"""


REGEN_PROMPTS = {
    "error": REGENERATE_QUERY_ON_ERROR,
    "empty_result": REGENERATE_QUERY_ON_EMPTY_RESULT,
}

GET_SCHEMA_PROMPT = """
You are given a list of tables available in a SQL database: {available_tables}
Choose which are candidate tables that might be relevant to answer the user's question to get their full schema.
User question: {user_question}

Additional Context : {schema_context}

Instruction Context : {instruction_context}

You will call the appropriate tool to get the schema for the candidate tables.
"""

QUESTION_SYNTHESIS_PROMPT = """
You are a context synthesizer for a database query system.
Your goal is to rewrite the user's current question into a complete, standalone sentence that can be answered by a SQL database.

USER'S CURRENT QUESTION: {user_question}
USER'S PREVIOUS QUESTION (for context): {last_user_question}

INSTRUCTIONS:
1. If the current question contains pronouns (it, them, those) or implicit references to the previous question, resolve them using the previous question's context.
2. If the current question is a completely new topic and does not relate to the previous question, drop the old context entirely and just rewrite the new question clearly.
3. Output ONLY the standalone rewritten question. Do not add any explanations, preambles, or conversational filler.
"""
