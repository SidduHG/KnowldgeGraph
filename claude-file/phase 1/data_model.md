# Data Model: Node and Edge Types

## Node Types

- **FILE**: any source file (.py, .ts, .go, .rs...)
- **MODULE**: package or directory with an init/index
- **CLASS**: class, interface, struct, enum
- **FUNCTION**: standalone top-level function
- **METHOD**: function that belongs to a class
- **VARIABLE**: module-level constant or variable
- **TYPE**: type alias, interface def, typedef

## Edge Types

- **DEFINES**: `FILE -> CLASS / FUNCTION / VARIABLE`
  *file contains this symbol*
  
- **IMPORTS**: `FILE -> FILE`
  *file imports from another file*
  
- **CALLS**: `FUNCTION / METHOD -> FUNCTION / METHOD`
  *direct invocation at call site*
  
- **INHERITS**: `CLASS -> CLASS`
  *extends or implements parent*
  
- **CONTAINS**: `CLASS -> METHOD / VARIABLE`
  *class owns this member*
  
- **USES**: `FUNCTION / METHOD -> VARIABLE / TYPE`
  *reads or references a symbol*
  
- **EXPORTS**: `FILE -> any symbol`
  *publicly exported from this file*
