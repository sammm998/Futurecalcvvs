# Pipe detection — protocol 2

What the microservice receives, what this application will accept back, and what
every field means. The schemas beside this file are the definition; this
explains them.

**What this document does not do.** It does not say how to detect a pipe, how to
find a scale bar, how to read a label, or how to compute anything. Those are the
service's own business. The test applied to every sentence here: could it be
broken without a single byte on the wire changing? If yes, it is somebody's
implementation and it does not belong in a contract.

`MANIFEST.json` states the bundle version and a sha256 per file. Check it after
unpacking.

---

## The exchange

1. The application POSTs a request. The service answers **HTTP 202** with an
   acknowledgement, immediately, without detecting anything yet.
2. The service detects, in its own time and its own way.
3. The service POSTs a result to the callback address configured on it.

HTTP 429 instead of 202 means the service is saturated and the application will
try later.

---

## Request

Schema: `detection-request.v2.schema.json`. Example:
`examples/detection-request.valid.json`.

| Field | Meaning |
| --- | --- |
| `protocolVersion` | Always `2`. Any other value: the application and the service disagree about what the rest of the body means, and neither should guess. |
| `drawingId` | The drawing this job is about. UUID. Echoed back. |
| `runId` | This job. UUID, minted by the application. Echoed back, and it is what ties a callback to a job — see **What the application accepts**. |
| `image` | base64 of a gzipped SVG. One variant; there is no field naming a format because there is one format. |
| `coordinateSpace` | The canvas the result must be expressed in. `width` and `height` in pixels. Origin top-left, x right, y down. |
| `assignmentMethod` | Which implementation assigns labels to pipes: `llm` or `dimension`. Required, no default. See **Assignment method**. |
| `output.includeScaleAndLengths` | Which side owns the physical numbers. See **Scale and length**. |

What the request deliberately does **not** carry:

- **No scale.** When the application wants one, it asks the service for it via
  the flag; it never supplies one for the service to confirm.
- **No callback address.** A caller that can name the callback can point the
  service at anything. The address is the service's own configuration.
- **No secrets.** Those are headers.
- **No file identity or revision.** `runId` identifies the job in the
  application's own registry. Echoed back through the service they would prove
  nothing.

---

## Assignment method

`assignmentMethod` names which implementation attaches labels to pipes:

| Value | What it means |
| --- | --- |
| `"llm"` | Assignment reasons over the sheet with a language model. |
| `"dimension"` | Assignment matches on the dimension read off the label against the dimension of the pipe. **No model is called in the assignment step.** |

Three rules, and each one is observable on the wire:

- **It is required, and there is no default.** A request without it, or with a
  value that is neither of the two, is refused with `400`. Filling one in would
  record a choice nobody made, and two runs of the same sheet are only worth
  comparing when each says how it was performed.
- **There is no fallback between the two.** A service that cannot perform the
  named method fails the run — `status: "failed"` with
  `error.code: "assignment_method_unavailable"` — rather than quietly performing
  the other one. A result that says nothing about which method produced it is
  the one thing this field exists to prevent.
- **It does not come back.** Neither the acknowledgement nor the result carries
  it. The application minted the `runId` and wrote the method against it in its
  own registry before dispatching; echoed back through the service it would
  prove nothing about what was actually run.

It sits beside the identifiers rather than under `output` because it selects how
the run is performed, not what the answer contains.

---

## Acknowledgement

Schema: `detection-ack.v2.schema.json`. Example:
`examples/detection-ack.valid.json`.

| Field | Meaning |
| --- | --- |
| `protocolVersion` | Always `2`. |
| `status` | Always `"accepted"`. A refusal is an HTTP status, not this body. |
| `drawingId`, `runId` | Echoed from the request, so the application can match the acknowledgement to what it sent. |

---

## Result

Schema: `detection-result.v2.schema.json`. Two variants told apart by `status`,
with nothing in common beyond the identifiers. Examples:
`examples/detection-result.valid.json`,
`examples/detection-result.no-scale.valid.json`,
`examples/detection-result.failed.valid.json`.

### Success

| Field | Meaning |
| --- | --- |
| `protocolVersion`, `drawingId`, `runId` | As in the request. |
| `status` | `"succeeded"`. |
| `coordinateSpace` | The space the coordinates below are in. It is the space the request named. |
| `scale` | `pixelsPerMm` and where it came from, or `null` for "not determined". |
| `pipes[]` | See below. |
| `labels[]` | See below. |
| `markers[]` | Optional. Absent reads as none. |
| `metadata` | Counts and warnings. Informational. |

A run that found nothing is a success with empty arrays, not a failure.

#### `pipes[]`

| Field | Meaning |
| --- | --- |
| `id` | Local to this response. The application maps it to a UUID on first acceptance; the same callback delivered twice does not create new objects. |
| `geometry` | `nodes` with an `id` and a position, and `edges` as pairs of node ids. **One connected undirected graph per pipe.** Branches and loops are fine. Two edges are joined when they share a node id and only then: equal coordinates join nothing, so a crossing is not a connection. A run that branches is one pipe, not several. |
| `length` | Present only when the request asked for it. See **Scale and length**. |
| `labelId` | The `id` of one entry in `labels[]`, or `null`. One label or none — never a list. |
| `confidence` | How sure the service is about this pipe. Informational. |

#### `labels[]`

| Field | Meaning |
| --- | --- |
| `id` | Local to this response, referenced by `pipes[].labelId`. |
| `box` | Where it sits: `x`, `y`, `width`, `height`, and `rotation` in degrees clockwise if it is not upright. |
| `name` | **The whole code as one string**, exactly as read: system index kept, and any height note the service could attach to it — `VS1-S13-12/W CL 3200 ÖFG`. Not split into system, material, dimension or method. The application parses it. |
| `confidence` | How sure the service is about the reading. Informational. |

#### `markers[]`

| Field | Meaning |
| --- | --- |
| `id`, `box`, `confidence` | As for a label. |
| `symbol` | The legend symbol, as printed or resolved: `WC`. |
| `labelId` | A label this marker relates to, or `null`. |

### Failure

| Field | Meaning |
| --- | --- |
| `status` | `"failed"`. |
| `error.code` | A short machine-readable reason. |
| `error.message` | Text for a human reading a log. |
| `error.retryable` | Whether trying the same job again could succeed. |

A failure is still delivered to the callback and still carries `runId`: a job
that ends badly must end, not hang.

---

## Scale and length

Every physical length in this protocol is in **millimetres**, and no field
carries a unit — neither a `unit` property nor a suffix on a name. Pixels appear
only in `length.px` and in coordinates. `pixelsPerMm` is the one name that
states units, because a ratio has to name both or it means nothing.

`output.includeScaleAndLengths` decides **who owns the physical numbers**, so
there is exactly one authoritative answer at a time:

| Flag | `scale` in the result | `length` in the result | Who owns the number |
| --- | --- | --- | --- |
| `false` | `null` | absent | the application, from `geometry` and its own scale |
| `true` | the scale the service determined, or `null` if it could not | present, computed by the service | the service |

Two things follow, and neither is a rule about how to compute:

- **A scale the service could not determine is `null`, and that is still a
  success.** `metadata.warnings` carries `scale_not_found`. A guessed scale is
  worse than none, because a wrong length looks exactly like a right one.
- **With no scale there is no `length.plan`.** Absent means unknown. The
  application will not read it as zero and will not substitute a default.

`length.px` is a distance in pixels of `coordinateSpace`; `length.plan` is the
same run in millimetres.

**What happens after import, so nobody wonders later.** When the service owns
the number, its value is what gets stored. If a user afterwards corrects the
scale by hand, the application recomputes from `geometry` — the service is not
there to be asked again. That is expected, and it is why `geometry` and not
`length` is the thing this protocol treats as the real content.

---

## What the application accepts

A result is rejected, and the run recorded as failed, when:

- **`protocolVersion` is not 2.**
- **The body carries a field the schema does not name.** The result schema is
  closed. This is an untrusted-input boundary: nothing outside this application
  decides what ends up in a document it renders and bills from. It also means a
  new field is a breaking change — see **Versioning**.
- **A limit is exceeded.** Nothing is trimmed to fit.

| | |
| --- | --- |
| Pipes | 5 000 |
| Nodes, total | 20 000 |
| Edges, total | 40 000 |
| Labels | 2 000 |
| Markers | 2 000 |
| Any text field | 256 characters |
| Body | 10 MiB |

- **An edge names a node that is not there**, a node id repeats, an edge joins a
  node to itself or has no length, or a pipe's graph is not connected.
- **A coordinate falls outside `coordinateSpace`**, with a pixel of tolerance
  for rounding. The bounding box of a rotated `box` is checked after rotation.
- **The signature does not verify**, the timestamp is outside the window, or
  `runId` names no job the application is waiting for.

The `*.invalid.json` files in `examples/` are bodies the application rejects.
They carry as much of the contract as the valid ones: run them and check that
they fail, or conformance has only proved a happy path.

---

## Authentication

**To the service.** TLS, with `X-API-Key` in a header. The service may accept
two keys at once, so a rotation has no window without one; which of them arrived
is the service's own comparison and not something the header states.

**To the application.** A separate HMAC key, held in both secret stores,
independent of the key above. This direction *does* name its key, because
verification has to choose one before it can compute a signature — a comparison
cannot be deferred the way a bearer token's can.

```
X-Key-Id: callback-key-2026-09
X-Timestamp: <Unix seconds>
X-Signature: v1=<hex HMAC-SHA256(key, UTF8(timestamp + ".") || rawBodyBytes)>
```

The signature is verified against the raw bytes before the body is parsed, with
a ±300 second window. The body must not be compressed, and nothing may alter it
in transit, or the bytes signed are not the bytes received. A test vector ships
with the bundle so an implementation can check itself without a round trip.

---

## Repeats

How and when to retry is the service's decision. What the application does with
a repeat is not, so it is stated here:

| The application receives | It answers |
| --- | --- |
| A `runId` it already accepted, with the same body | `200` and the original receipt. Nothing is stored twice. |
| A `runId` it already accepted, with a different body | `409`. Nothing is overwritten. |
| A `runId` it has no record of | Rejected. Receipts are kept at least 7 days; deliveries are accepted for 24 hours. |
| Any of the above | The same authentication as a first delivery. An unauthenticated body cannot mark any job as failed. |

A `2xx` means delivered. It does not mean the result has been applied to the
drawing: a result that would overwrite work someone did by hand waits for a
person, and the service has nothing to do with that.

---

## Versioning

`protocolVersion` in the payload is the wire version, currently `2`. The bundle
version in `MANIFEST.json` is the version of these files; a bundle may gain a
minor version without the wire version moving.

Because the result schema is closed, a new field is a breaking change and the
order is fixed: a new contract version is published, the service implements it,
then the application starts consuming it. A field sent before the contract
carries it fails validation on arrival and the run is recorded as failed.

`output.includeScaleAndLengths` exists so that moving the length computation
between the two sides is a change to one parameter rather than a change to this
protocol.

**2.0.2 added `assignmentMethod`, and it is required.** A request that predates
it no longer validates, so the order is the one above and it is not optional:
publish the bundle, have the service accept and route the new field, and only
then have the application start sending it. The wire version stays `2` — the
result shape did not move — but a service pinned to 2.0.1 will refuse every
request from an application on 2.0.2, which is the ordering doing its job rather
than a fault.
