# What is this file?

This file tells ai coding agents about the conventions and expected practices when interacting with this code base.

# When to make sure of information in this file?

Use it EVERYTIME you write any code.

# Rules of engagement

The following list of rules is true no matter what kind of code you're writing, frontend, backend, tests, or even deployment scripts.

1. Minimal code change that satisfies the user's ask. If the user's precise ask is unclear, you MUST clarify. Optionally, get the user to explicitly sign off on the change set if the change required is medium sized and above. 
2. Do not speculate what the user wants. Just ask.
3. KISS in general. Simple architecture, simple code patterns, minimal external dependencies. 
4. When discussing with the user, like in a code deep dive for example, you should always be concise with your answers. Wall of text is not the right way to format responses. Responses to technical discussion should be short, concise, and in bullet point form where required. You should SACRIFICE grammatical correctness for concision. 

# Coding standards

This is how you know you've written good code by my definition.

1. Your code is modularized-as-needed. The signs: your changes are not a thin modules, your changes are only in a module IFF its theoretically a medium likelihood replaceable component (as long as contract is kept the same).
2. (Future, not yet now) Your code changes come with some form of test. Ideally its a e2e test and or UAT test but if not ameanable to those higher level testing then at least a unit test. Happy, sad, and common edge cases need to be tested.

> Note: You shouldn't be eagerly write tests until the user has confirmed that the code looks correct enough to start testing. Otherwise you might be wasting the user's time and tokens if the user is not happy with the code changes yet.