# RFC 8785 reference data

Source: https://github.com/cyberphone/json-canonicalization/tree/19d51d7fe467d4706a3ff08adf8a748f29fc21e0/testdata

The six input/output/outhex triples are copied without content changes from
the reference implementation. `outhex` is the authoritative byte comparison,
independent of checkout line endings. Copyright and license: see `LICENSE`.

The upstream numeric corpora are not vendored: Taxo relies on these six documents
and on its own identity vectors, which cover the numbers accepted by the contract.

These are raw JCS tests: do not NFC-normalize their inputs. Taxo applies NFC
before JCS in its separate identity vectors. Numeric reference inputs are parsed
as binary64, while Taxo additionally rejects JSON integers outside its safe range.
