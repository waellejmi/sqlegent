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
