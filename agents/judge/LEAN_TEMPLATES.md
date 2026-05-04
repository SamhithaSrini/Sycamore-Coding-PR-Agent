# Lean4 Proposition Templates

## Sorting / Ordering
```lean4
theorem sorted_output (input : List Int) :
  isSorted (mySort input) = true
```

## Length Preservation
```lean4
theorem preserves_length (lst : List α) (f : α → α) :
  (lst.map f).length = lst.length
```

## Mathematical Operations
```lean4
theorem factorial_positive (n : Nat) :
  factorial n > 0

theorem factorial_zero :
  factorial 0 = 1
```

## Idempotency
```lean4
theorem idempotent (x : α) [DecidableEq α] :
  f (f x) = f x
```

## Commutativity
```lean4
theorem commutative (a b : Int) :
  myAdd a b = myAdd b a
```

## Bounds
```lean4
theorem result_in_range (n : Nat) (h : n > 0) :
  0 < myFunc n ∧ myFunc n ≤ n
```

## Tactics Reference
- `omega`        : linear arithmetic over Int/Nat
- `simp`         : simplification with simp lemmas
- `ring`         : ring/field algebra
- `decide`       : decidable propositions (finite cases)
- `norm_num`     : numeric normalization
- `native_decide`: evaluated natively for performance
- `induction`    : structural induction
