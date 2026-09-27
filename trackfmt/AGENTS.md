# Repository Guidelines

## Git

- Use Git only for read-only inspection. Never run any Git operation that writes or changes repository state, including staging, committing, amending, rebasing, merging, resetting, restoring, checking out, switching, creating or deleting branches or tags, modifying remotes or configuration, or pushing.

## Naming

- Prefix non-public implementation details with a single underscore. Do not use double-leading-underscore names unless name mangling is required.
- Name functions with a verb that describes the action they perform.

## Code style

- Do not introduce blank lines between import statements.
- Do not put blank lines in functions shorter than 20 lines.
- Use comprehensions only when they remain easy to read. Use an explicit loop for multi-step logic or side effects.
- Prefer functions that do not mutate their arguments. Clearly document mutation when it is necessary.
- Use `pathlib.Path` for filesystem paths instead of manually manipulating path strings.

## Type annotations

- Add type annotations whenever the type is straightforward, especially for primitives, standard containers, and small unions. An annotation may be omitted when expressing it accurately would be disproportionately complex or would make the code harder to understand.
- Do not introduce a class solely to express a type annotation. A class is appropriate when the implementation needs it for runtime behavior, such as parsing or validation.
- Annotate module-level variables when their type is not obvious from the assigned value.

## Documentation and comments

- Give every top-level declaration a concise explanatory comment, even if it has a docstring.
- Add concise docstrings to public declarations, but never to test or stub files.
- Document non-public code, parameters, return values, exceptions, and side effects only when they are not obvious.
