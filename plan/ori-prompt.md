we have so far implemented a backend and frontend for our app. but through this process we haven't worried too much about code quality. its payback time. the goal is this:

refactor our code so that we can have confidence to move forward with more coding without speed degradation.

here's how we'll be doing it:

1. aggressively refactor BE
2. ask for feedback and resolve feedback in a loop until satisfied
3. aggressively refactor FE
4. ask for feedback and resolve feedback in a loop until satisfied
5. add mockers for the actual api calls
6. write uat tests

what does aggresively refactor mean: 0. DO NOT MODIFY EXISTING BEHAVIOR

1. modularize code such that the code is more "composable". meaning, if this is a feature like "generate token usage report", it can theoretically be replaced by another algorithm easily as long as the contract is identical, then this is a good candidate for refactoring. another example might be response building.
2. no god functions.
3. remove dead code or unused features
4. in general, you should be removing lines of code rather than adding lines of code as a sign of success

how to write uat tests:

1. create a mocker function for calling actual llms or email creation
2. in the uat test you may instantiate your own .db file and create scenarios with sql files for you to test out cases.
3. the uat test should be backend scoped only. meaning, the uat test will start at calling api endpoints. and the verification is in the expected number of calls to certain functions, expected db state, and expected api call output.
4. uat tests should cover happy, sad, and common edge cases.
5. a lot of components in the uat test code are going to be repeated again and again. you should implement a harness for all the common code so that each test looks more declarative than imperative.

your job now:
write a plan into a few .md files that breaks all this work down into stages. in each stage mention the work you'll be doing, why, and guidelines/guardrails you'll be following strictly. the .md files should have enough context so that i may pass each .md file into a separate llm. i will be executing each .md file sequentially, so the .md file should have a sequence number informing me which .md file title i should be sending in what order. now, importantly, even within the .md files, its important that the agent breaks the task down into many smaller verifiable steps!
