or should i just use one general model to do all ?  Also I am tasking with market analysis and to see the features i want to implement 
I am working on a project : its core is  A Natural Language To SQL, later I will be adding a lot of features  such as visualization , optimisation requests for admin users , multiple DB support and multiple AI integration (local , cloud api). I will be creating a CLI and Web version . I am thinking of using python due to familarity .  Later I will work on  these features and small details but i should start with the core. I am tasked with market analysis to see all the features in existing solutions and which features are missing and i want  to implement them in my project. 
i need to benchmark  exisitngs solutions and critique them.

This is my search so far composing mostly of open source projects : 

Try to search for more paid solutions and closed source, for each tell me its features and which are missing.for example i saw Tableau AskData.

and These are my ideas:

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

