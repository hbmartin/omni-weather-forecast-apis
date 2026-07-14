# Keep persistent timezone caching in the CLI

The CLI owns a persistent coordinate-to-IANA-timezone cache beside its forecast
database because scheduled collection must avoid repeated timezone lookups, while
the library remains storage-agnostic for embedding applications. Library callers
may supply a location timezone on each forecast request; normalization prefers
valid provider-supplied IANA metadata, then the caller value, and finally an
uncached Open-Meteo coordinate lookup. This keeps persistence policy out of the
library without sacrificing a correctness-preserving fallback.
