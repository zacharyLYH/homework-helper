# What is this file?

This file tells ai coding agents about the conventions and expected practices when interacting with this code base.

# When to make sure of information in this file?

Use it EVERYTIME you write any code.

# Overall rules that apply to every scenario

The following list of rules is true no matter what kind of code you're writing, frontend, backend, tests, or even deployment scripts.

1. Minimal code change that satisfies the user's ask. If the user's precise ask is unclear, you MUST clarify. Optionally, get the user to explicitly sign off on the change set if the change required is medium sized and above. 
2. Do not speculate what the user wants. Just ask.
3. KISS in general. Simple architecture, simple code patterns, minimal external dependencies. 
4. When discussing with the user, like in a code deep dive for example, you should always be concise with your answers. Wall of text is not the right way to format responses. Responses to technical discussion should be short, concise, and in bullet point form where required. You should SACRIFICE grammatical correctness for concision. 

# Coding standards in general

This is how you know you've written good code by my definition.

1. Your code is modularized-as-needed. The signs: your changes are not a thin modules, your changes are only in a module IFF its theoretically a medium likelihood replaceable component (as long as contract is kept the same).
2. (Future, not yet now) Your code changes come with some form of test. Ideally its a e2e test and or UAT test but if not ameanable to those higher level testing then at least a unit test. Happy, sad, and common edge cases need to be tested.
3. There are industry established coding standards for the technologies we're using. We should always try to align as a default, and deviate only if the user explicitly deviates. But, it should then be documented why we're not following best practices. 

> Note: You shouldn't be eagerly write tests until the user has confirmed that the code looks correct enough to start testing. Otherwise you might be wasting the user's time and tokens if the user is not happy with the code changes yet.

# Per technology specific standards

## Python backend
1. Most code Python should be typed. Only where it is very cumbersome to create/maintain a type are you allowed to use `Any` type or ask to ignore type checking by the LSP.
2. On code change complete, run `uv run pyright app/` to make sure no LSP issues.
3. To  In VSCode do `Cmd + ,`. Search for `python.analysis.typeCheckingMode`. Change from `Off` to `Standard`. This activates the LSP.

## React frontend
1. Sparingly use advanced hooks, only if performance of some component is critical should you use advanced hooks. Otherwise stick to simple ones like `useState()` and `useEffect()`
2. A loaded prop definition is hard to work with and naturally scales the lines of code in some module. In general we try to minimize the number of props per component.
3. Make use of polished shadcn UI components where possible. The user might not make it explicit of the UI they want, but you should use common sense to try to fit shadcn UI components where it makes sense. Inventing your own UI components should only happen if the user has expressed unhappiness with existing UIs and explicitly describes how they want a component to look.

## Sqlite DB
1. On every database change like adding a new column, make sure to update `purge-and-seed.sql`. This `sql` file is a mini representation of our data-backed features.
