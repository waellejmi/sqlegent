or should i just use one general model to do all ?  Also I am tasking with market analysis and to see the features i want to implement 
I am working on a project : its core is  A Natural Language To SQL, later I will be adding a lot of features  such as visualization , optimisation requests for admin users , multiple DB support and multiple AI integration (local , cloud api). I will be creating a CLI and Web version . I am thinking of using python due to familarity .  Later I will work on  these features and small details but i should start with the core. I am tasked with market analysis to see all the features in existing solutions and which features are missing and i want  to implement them in my project. 
i need to benchmark  exisitngs solutions and critique them.

This is my search so far composing mostly of open source projects : 
# Market Analysis
## Open-Source Solutions
- [vanna](https://github.com/vanna-ai/vanna)
```
+ RBAC (admin = more rights, user see only what he is concerend with) 
+ oss 
+ visulisations
- DB prober (Select DB from multiple that are running )
- DB provider supports (Cloud, Docker , Local , Distrubeted )
```
- [WrenAI](https://github.com/Canner/WrenAI)
[Documentation](https://docs.getwren.ai/oss/concept/wren_ai_service) 
```
+ visulisations saved to a seperate dashboard tab. (maybe add a cron job to update the graph for the saved request )
+ multiple DB support plus Local AI integration.
+ Modeling Definition Language (MDL) for structured output 
+ Clear Documentation
```
- [sqlchat](https://github.com/sqlchat/sqlchat)
```
+ multiple DB support
+ confirmation before executing the generated SQL
+ token limit for converstation prompt 
- db schema is in the prompt (We Let THE LLM decide = risk of hallucinations and TOkens wasted )
```
- [dataherald](https://github.com/Dataherald/dataherald/tree/main)
```
+ core sepreration: Engine(core lang2sql), enterprise (for auth, orgs, usrs), admin console (GUI) , slackbot (for slack integration) {not needed but good for context}
- missing normal user GUI 
```
- [nao](https://github.com/getnao/nao)
```
+ framework like structure (it creates a directory with subfolders for each component: DBs, Documents , Rules)
+ fetches 10 rows from dataset to show examples for the moodel 
+ exctracts db schema and transform it to md.
- relying too much on the LLM to understand the schema if not specified in the prompt
```
### Benchmarks on Datasets
- [list of Text-to-SQL Models](https://github.com/eosphoros-ai/Awesome-Text2SQL)
- [Agentar-Scale-SQL Framework + results](https://github.com/antgroup/Agentar-Scale-SQL/tree/main)
### Extras 
- [NL2SQL Handbook](https://github.com/HKUSTDial/NL2SQL_Handbook)
- [Data Agents Handbook](https://github.com/HKUSTDial/awesome-data-agents)
- [intressting OPENAI implementation](https://openai.com/index/inside-our-in-house-data-agent/)
- [pandas-ai library](https://github.com/sinaptik-ai/pandas-ai)
- [useful blog plus implementation](https://bytes.swiggy.com/hermes-a-text-to-sql-solution-at-swiggy-81573fb4fb6e)
## Paid and closed source solutions:
- [Salesforce Tableau AskData](https://www.tableau.com/learn/tutorials/on-demand/ask-data)
- [Snowflake Cortex](https://www.snowflake.com/en/product/features/cortex/)


Try to search for more paid solutions and closed source, for each tell me its features and which are missing.for example i saw Tableau AskData.

and These are my ideas:

- create CLI ver and self hosted UI ver for this SQL AI agent
- Support distributed databases(Views may not contain full db schema sometimes).
- DB Prober (MySQL, Postgres, MongoDB) 
- Docker DBs, Local DBs, Cloud DBs support
- Add autocomeplete for DB names, table names, column names 
- add a toggle to verify sql before executing it (show the generated SQL and ask for confirmation before executing it)
- add a sql injection prevention mechanism (e.g. check for certain keywords or patterns in the generated SQL and block execution if they are detected)
- implement a mulit agent system where we have a orchestor agent that receives the user query then calls the Text2SQL to generate 
- keep a register of queries  to cache results 
- log failed requests for manual review 


I keep seeing a lot of papers about Text2SQL or NL2SQL, are they working on creatings LLMs that generate SQL from natural language or are they working on Agnets that use big general LLMs like gpt  ? Also in big benchmarks like SPIDER And BIRD from the leaderboards, i keep seeing these results:

AskData + GPT-4o
Agentar-Scale-SQL
LongData-SQL
Zhiwen-Lingsi-Agent
DeepEye-SQL
Q-SQL
MIC2-SQL
SiriusAI-Text2SQL-Agent
CHASE-SQL + Gemini
JoyDataAgent-SQL

and 

MiniSeek
DAIL-SQL + GPT-4 + Self-Consistency
DAIL-SQL + GPT-4
DPG-SQL + GPT-4 + Self-Correction

Are these agents or multiple LLMs ? 

My question is should i look into a creating a multi agent system where i have an orchestartor ( this is the one who interacts with user ) , and a NL2SQL agent (model) for creating the needed SQL then the orchestrator tries to exectue it and return results. or will this overcomplicate stuff ? should i go for a big enough model ?

