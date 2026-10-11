"""Build an independently frozen full-document RFC corpus and manual inventory.

No model is called. Full original bytes (including notices) are preserved. The
page-type source record is a logical full-text container, NOT a PDF/visual page.
Only the downstream corpus's existing mechanical windows split the text. All
proofs are checked before publishing any fixture. Questions never select corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_HASHES = {
    "rfc2119": "3c2ceb7bfc84cd34720f4a5271338ab9d8280d34bdd1eb250c64306202f2ed8b",
    "rfc8259": "61a5378f4255c720beb2a4b4a63b29540147c140f36988bf086291989b4cd2d7",
    "rfc7493": "a44ccf1451a7bf4f4bbb78b39e10ed0e9a27ff2ee5b639c6458042b5a7197062",
    "rfc9000": "f88aae47f8b18e102024916e975e919201d8dde689cba79b01079eaedd402e22",
    "rfc9001": "3bbaecdf5afd278052a2c48348ce118c4ff8d0cf6b9915549858171b3f98a591",
}


def inventory_questions():
    questions = []

    def requirement(doc, text, *quotes, notes=""):
        return {"text": text, "proofs": ([{"doc_key": doc, "chunk_id": doc + "-fulltext",
                                           "quotes": list(quotes)}] if quotes else []), "gold_notes": notes}

    def question(identity, split, cluster, docs, query, requirements, missing=False):
        questions.append({"id": identity, "split": split, "cluster_id": cluster,
                          "doc_keys": docs, "query": query,
                          "answerability": "unanswerable" if missing else "answerable",
                          "gold_notes": "Only the supplied full RFC texts count. Preserve normative strength and conditions; no external facts.",
                          "requirements": [{"id": f"{identity}.r{index}", **r}
                                           for index, r in enumerate(requirements, 1)]})

    r = requirement
    for number, (topic, query, requirements, missing) in enumerate([
        ("absolute", "In RFC 2119, compare MUST and MUST NOT and give their synonymous terms.", [
            r("rfc2119", "MUST/REQUIRED/SHALL is an absolute requirement.", '1. MUST   This word, or the terms "REQUIRED" or "SHALL", mean that the\n   definition is an absolute requirement of the specification.'),
            r("rfc2119", "MUST NOT/SHALL NOT is an absolute prohibition.", '2. MUST NOT   This phrase, or the phrase "SHALL NOT", mean that the\n   definition is an absolute prohibition of the specification.')], False),
        ("recommendations", "How do RFC 2119 SHOULD and SHOULD NOT allow exceptions, and what must implementors consider before deviating?", [
            r("rfc2119", "SHOULD allows valid exceptions only after understanding and weighing full implications.", 'may exist valid reasons in particular circumstances to ignore a\n   particular item, but the full implications must be understood and\n   carefully weighed before choosing a different course.'),
            r("rfc2119", "SHOULD NOT permits acceptable/useful exceptions after understanding and weighing full implications.", 'particular behavior is acceptable or even useful, but the full\n   implications should be understood and the case carefully weighed\n   before implementing any behavior described with this label.')], False),
        ("optional", "Under RFC 2119 MAY/OPTIONAL, what obligations apply both to implementors who include an option and those who omit it?", [
            r("rfc2119", "MAY/OPTIONAL is truly optional.", '5. MAY   This word, or the adjective "OPTIONAL", mean that an item is\n   truly optional.'),
            r("rfc2119", "Both including and omitting implementations must interoperate, potentially without the optional functionality.", 'An implementation which does not include a particular option MUST be\n   prepared to interoperate with another implementation which does\n   include the option, though perhaps with reduced functionality.', 'MUST be prepared to interoperate with another implementation which\n   does not include the option')], False),
        ("imperatives", "Where does RFC 2119 permit the use of these imperatives, and can they impose an implementation method unnecessary for interoperability?", [
            r("rfc2119", "Use imperatives sparingly only for interoperability or limiting potentially harmful behavior.", 'they MUST only be used where it is\n   actually required for interoperation or to limit behavior which has\n   potential for causing harm'),
            r("rfc2119", "Do not impose a method unnecessary for interoperability.", 'they must not be used to try to impose a particular method\n   on implementors where the method is not required for\n   interoperability.')], False),
        ("security", "What does RFC 2119 ask authors to explain about security implications of noncompliance, and why?", [
            r("rfc2119", "Security effects of failing MUST/SHOULD or violating prohibitions may be subtle.", 'The effects on security of not implementing a MUST or\n   SHOULD, or doing something the specification says MUST NOT or SHOULD\n   NOT be done may be very subtle.'),
            r("rfc2119", "Explain implications because implementors may lack the authors' experience and discussion.", 'elaborate the security implications of not following\n   recommendations or requirements as most implementors will not have\n   had the benefit of the experience and discussion that produced the\n   specification.')], False),
        ("missing-observation", "What is the RFC 2119 meaning of MUST, and what measured percentage of deployed products complied with MUST requirements in 2025?", [
            r("rfc2119", "MUST is an absolute requirement.", 'definition is an absolute requirement of the specification.'),
            r("rfc2119", "Give the measured 2025 deployed-product compliance percentage.", notes="Unavailable: a requirements-language definition is not a deployed-product compliance study.")], True),
    ], 1):
        question(f"rfc-dev-{number:03d}", "development", "bcp14/" + topic, ["rfc2119"], query, requirements, missing)

    json_cases = [
        ("duplicate-names", "Compare RFC 8259 and RFC 7493 on duplicate object member names, including the normative strength and I-JSON's definition of duplicate.", [
            r("rfc8259", "RFC 8259 says names SHOULD be unique, not MUST.", 'The names within an object SHOULD be unique.'),
            r("rfc7493", "I-JSON MUST NOT have duplicates; compare Unicode sequences after processing escapes.", 'Objects in I-JSON messages MUST NOT have members with duplicate\n   names.  In this context, "duplicate" means that the names, after\n   processing any escaped characters, are identical sequences of Unicode\n   characters.')], False),
        ("encoding-bom", "Compare the UTF-8 encoding scope in RFC 8259 and I-JSON RFC 7493; also state how RFC 8259 handles a networked byte order mark.", [
            r("rfc8259", "Open-ecosystem exchange MUST use UTF-8; generators MUST NOT add BOM and parsers MAY ignore it.", 'JSON text exchanged between systems that are not part of a closed\n   ecosystem MUST be encoded using UTF-8', 'Implementations MUST NOT add a byte order mark (U+FEFF)', 'implementations that parse JSON texts MAY ignore\n   the presence of a byte order mark'),
            r("rfc7493", "All I-JSON messages MUST be UTF-8.", 'I-JSON messages MUST be encoded using UTF-8')], False),
        ("numeric-precision", "What exact integer range is interoperable under RFC 8259, what numeric capabilities may I-JSON assume, and how does RFC 7493 recommend conveying larger exact numbers?", [
            r("rfc8259", "Exact interoperable integers lie in [-(2**53)+1, (2**53)-1].", 'numbers that are integers and\n   are in the range [-(2**53)+1, (2**53)-1] are interoperable'),
            r("rfc7493", "Do not assume magnitude/precision beyond binary64; SHOULD NOT exceed it; strings are RECOMMENDED for larger exact numbers.", 'Implementations that generate I-JSON messages cannot assume that\n   receiving implementations can process numeric values with greater\n   magnitude or precision than provided by those numbers.', 'messages SHOULD NOT include numbers that express greater magnitude or\n   precision than an IEEE 754 double precision number provides,', 'it is RECOMMENDED to encode them in\n   JSON string values.')], False),
        ("top-level", "Can RFC 8259 JSON and RFC 7493 I-JSON have top-level scalar values, and what does I-JSON recommend for older receivers?", [
            r("rfc8259", "A JSON text is any serialized value, not limited to object/array.", 'A JSON text is a serialized value.'),
            r("rfc7493", "I-JSON permits any value but SHOULD NOT use non-object/non-array top-level values for maximum compatibility with old receivers.", 'An I-JSON message can be any JSON value.', 'protocol designers SHOULD NOT use top-level JSON texts that are\n   neither objects nor arrays.')], False),
        ("surrogates", "Contrast RFC 8259's grammar allowance and behavior for unpaired UTF-16 surrogates with RFC 7493's character restrictions, including escaped characters.", [
            r("rfc8259", "JSON ABNF permits unpaired surrogate bit sequences, with unpredictable receiver behavior.", 'ABNF in this specification allows member names and\n   string values to contain bit sequences that cannot encode Unicode\n   characters;', 'The behavior of software that\n   receives JSON texts containing such values is unpredictable;'),
            r("rfc7493", "I-JSON forbids surrogate/noncharacter code points in names/strings, whether direct or escaped; unpaired \\uDEAD is invalid but a valid pair is legal.", 'MUST NOT include code points that identify Surrogates or\n   Noncharacters', 'This applies both to characters encoded directly in UTF-8 and to\n   those which are escaped; thus, "\\uDEAD" is invalid because it is an\n   unpaired surrogate, while "\\uD800\\uDEAD" would be legal.')], False),
        ("parser-generator", "Under RFC 8259, distinguish a parser's required acceptance, optional extensions, and implementation limits from a generator's conformance obligation.", [
            r("rfc8259", "Parser MUST accept conforming texts and MAY accept extensions.", 'JSON parser MUST accept all texts that conform to the JSON grammar.', 'A JSON parser MAY accept non-JSON forms or extensions.'),
            r("rfc8259", "Limits on size/depth/numeric range/strings are allowed; generated text MUST strictly conform.", 'An implementation may set limits on the size of texts', 'An implementation may set limits on the maximum depth of\n   nesting.', 'An implementation may set limits on the range and precision\n   of numbers.  An implementation may set limits on the length and\n   character contents of strings.', 'The resulting text MUST\n   strictly conform to the JSON grammar.')], False),
        ("string-comparison", "How does RFC 8259 recommend interoperable string equality checks, why can escaped-string comparison be wrong, and which characters must be escaped?", [
            r("rfc8259", "Convert representation to Unicode code units and compare numerically; unconverted escapes can incorrectly distinguish equal strings.", 'textual representation into sequences of Unicode code units and then\n   perform the comparison numerically, code unit by code unit', 'implementations that compare strings with escaped characters\n   unconverted may incorrectly find that "a\\\\b" and "a\\u005Cb" are not\n   equal.'),
            r("rfc8259", "Escape quotation mark, reverse solidus, and controls U+0000 through U+001F.", 'characters that MUST be escaped:\n   quotation mark, reverse solidus, and the control characters (U+0000\n   through U+001F).')], False),
        ("values-arrays", "According to RFC 8259, enumerate the allowed literal names and their case, and say whether array elements must all share a type.", [
            r("rfc8259", "false, null and true are the only literal names and MUST be lowercase.", 'false\n      null\n      true', 'The literal names MUST be lowercase.  No other literal names are\n   allowed.'),
            r("rfc8259", "Array values need not share one type.", 'There is no requirement that the values in an array be of the same\n   type.')], False),
        ("timestamps-binary", "What representation and additional formatting restrictions does RFC 7493 recommend for timestamps and durations, and what encoding for arbitrary binary data?", [
            r("rfc7493", "ISO8601/RFC3339 strings with uppercase letters, explicit timezone and seconds even 00; durations use Appendix A production with same restrictions.", 'data\n   items be expressed as string values in ISO 8601 format', 'uppercase rather\n   than lowercase letters be used, that the timezone be included not\n   defaulted, and that optional trailing seconds be included even when\n   their value is "00".', 'containing time durations conform to the "duration" production in\n   Appendix A of RFC 3339, with the same additional restrictions.'),
            r("rfc7493", "Binary data is RECOMMENDED as a base64url string.", 'it is RECOMMENDED that this data be encoded in a string\n   value in base64url;')], False),
        ("must-ignore", "In RFC 7493, how should a Must-Ignore protocol process an unknown element, and what top-level/member design supports it?", [
            r("rfc7493", "Treat transaction as though unknown element absent; MUST NOT make it an error.", 'it should treat the rest of the protocol transaction as if\n   the new element simply did not appear, and in particular, the\n   implementation MUST NOT treat this as an error condition.'),
            r("rfc7493", "Require object top level and specify unknown member names MUST be ignored.", 'require that top-level protocol elements must be JSON\n   objects, and to specify that members whose names are unrecognized\n   MUST be ignored.')], False),
        ("missing-adoption", "What normative strength does RFC 8259 use for unique object names, and what measured percentage of production JSON parsers adopted I-JSON in 2025 do these RFCs report?", [
            r("rfc8259", "RFC 8259 uses SHOULD for unique names.", 'The names within an object SHOULD be unique.'),
            r("rfc7493", "Provide measured 2025 production-parser I-JSON adoption percentage.", notes="Unavailable: normative interoperability guidance is not an adoption survey.")], True),
        ("missing-latency", "What is RFC 7493's exact-integer interoperability threshold, and what measured median parsing latency in milliseconds for 1-megabyte I-JSON messages is reported?", [
            r("rfc7493", "Integers with absolute value greater than 9007199254740991 cannot be expected to be exact.", 'absolute value is greater than 9007199254740991', 'as an exact value.'),
            r("rfc7493", "Provide measured median 1MB-message parsing latency in milliseconds.", notes="Unavailable: a numeric precision threshold is not a timing benchmark.")], True),
    ]
    for number, (topic, query, requirements, missing) in enumerate(json_cases, 1):
        question(f"rfc-held-{number:03d}", "held_out", "json/" + topic,
                 ["rfc8259", "rfc7493"], query, requirements, missing)

    quic_cases = [
        ("stream-table", "From RFC 9000 Table 1, give the four stream-ID bit patterns with initiator/direction, then state the stream-ID width and whether reuse within a connection is allowed.", [
            r("rfc9000", "Map 0x00 client-bidi, 0x01 server-bidi, 0x02 client-uni, 0x03 server-uni without dropping table columns.", '| 0x00 | Client-Initiated, Bidirectional  |', '| 0x01 | Server-Initiated, Bidirectional  |', '| 0x02 | Client-Initiated, Unidirectional |', '| 0x03 | Server-Initiated, Unidirectional |'),
            r("rfc9000", "Stream ID is 62-bit 0..2^62-1 and MUST NOT be reused within a connection.", 'A stream ID is a 62-bit integer (0 to\n   2^62-1)', 'endpoint MUST NOT reuse a stream ID within a connection.')], False),
        ("integer-table", "Reproduce the length, usable bits and range for each QUIC variable-length integer prefix in RFC 9000 Table 4, and identify the minimum-length exception and integer fields not using this encoding.", [
            r("rfc9000", "Map prefixes 00/01/10/11 to 1/2/4/8 bytes, 6/14/30/62 bits and exact ranges from Table 4.", '| 00   | 1      | 6           | 0-63                  |', '| 01   | 2      | 14          | 0-16383               |', '| 10   | 4      | 30          | 0-1073741823          |', '| 11   | 8      | 62          | 0-4611686018427387903 |'),
            r("rfc9000", "Minimal encoding is not required except Frame Type; versions, header packet numbers and long-header connection-ID lengths do not use it.", 'Values do not need to be encoded on the minimum number of bytes\n   necessary, with the sole exception of the Frame Type field;', 'Versions (Section 15), packet numbers sent in the header\n   (Section 17.1), and the length of connection IDs in long header\n   packets (Section 17.2) are described using integers but do not use\n   this encoding.')], False),
        ("anti-amplification", "Combine RFC 9000's pre-validation byte limit with RFC 9001's explanation of certificate-chain size, and state the client Initial UDP-payload minimum.", [
            r("rfc9000", "Before validation server MUST NOT send over 3 times received bytes; client Initial UDP payload MUST be >=1200 bytes with padding.", 'servers MUST NOT send more\n   than three times as many bytes as the number of bytes they have\n   received.', 'Clients MUST ensure that UDP datagrams containing Initial packets\n   have UDP payloads of at least 1200 bytes, adding PADDING frames as\n   necessary.'),
            r("rfc9001", "Certificate chains consume bytes and size control is critical because server is limited to 3 bytes per received byte before validation.", 'the size of the certificate chain can consume a large number of\n      |  bytes.', 'servers are limited to sending 3\n      |  bytes for every byte received prior to validating the client\n      |  address;')], False),
        ("idle-timeout", "According to RFC 9000, give max_idle_timeout's unit, how two advertised values or a sole nonzero value determine the effective timeout, the PTO floor, and the both-zero/omitted case.", [
            r("rfc9000", "max_idle_timeout is in milliseconds; disabled if both omit or set zero.", 'The maximum idle timeout is a value in\n      milliseconds', 'Idle timeout is disabled when both endpoints omit this transport\n      parameter or specify a value of 0.'),
            r("rfc9000", "Use minimum of two advertised values or sole nonzero value, with period >=3 times current PTO.", 'minimum of the two advertised\n   values (or the sole advertised value, if only one endpoint advertises\n   a non-zero value).', 'increase the idle timeout period to be at least three times the\n   current Probe Timeout (PTO).')], False),
        ("ack-delay", "Compare RFC 9000 ack_delay_exponent and max_ack_delay: defaults, meaning/unit, and invalid values.", [
            r("rfc9000", "Exponent defaults to 3 (multiplier8); values above20 invalid.", 'default value of 3 is assumed (indicating a multiplier of 8).\n      Values above 20 are invalid.'),
            r("rfc9000", "Max ACK delay is milliseconds, default25ms, >=2^14 invalid.", 'maximum amount of time in milliseconds', 'default of 25 milliseconds is\n      assumed.  Values of 2^14 or greater are invalid.')], False),
        ("tls-versions", "According to RFC 9001, which older TLS versions may QUIC clients offer, what if an older version is negotiated, and under what condition may a newer version be used?", [
            r("rfc9001", "Client MUST NOT offer TLS<1.3; endpoint MUST terminate if older version negotiated.", 'Clients MUST NOT offer TLS versions older than 1.3.', 'An endpoint MUST terminate the connection if a\n   version of TLS older than 1.3 is negotiated.'),
            r("rfc9001", "Newer TLS acceptable if it supports the TLS1.3 features QUIC uses.", 'acceptable provided that the features of TLS 1.3 that are used by\n   QUIC are supported by the newer version.')], False),
        ("early-data-limit", "Using RFC 9001 and RFC 9000, explain the NewSessionTicket max_early_data_size sentinel, what actually bounds QUIC 0-RTT data, and what initial_max_data means.", [
            r("rfc9001", "Sentinel is 0xffffffff, not a byte budget; initial_max_data controls QUIC 0RTT amount; absent early_data means no acceptance.", 'sentinel value 0xffffffff', 'To indicate that the server does not accept\n   0-RTT data, the early_data extension is omitted', 'QUIC 0-RTT is controlled by the initial_max_data transport parameter'),
            r("rfc9000", "initial_max_data is initial maximum total connection data, equivalent to immediately sending MAX_DATA after handshake.", 'initial value for the maximum\n      amount of data that can be sent on the connection.', 'equivalent to sending a MAX_DATA')], False),
        ("retry-not-hrr", "In RFC 9001 distinguish TLS HelloRetryRequest from QUIC Retry/Version Negotiation regarding 0-RTT rejection, and state server/client obligations after rejection.", [
            r("rfc9001", "HelloRetryRequest always rejects0RTT; rejecting server MUST NOT process0RTT packets.", 'A server will always reject 0-RTT if it sends\n   a TLS HelloRetryRequest.', 'When rejecting 0-RTT, a server MUST NOT\n   process any 0-RTT packets'),
            r("rfc9001", "Client MUST reset streams/application-bound state after rejection; Retry/Version Negotiation do not signify rejection and client MAY reattempt.", 'client therefore MUST reset the state of all\n   streams, including application state bound to those streams.', 'A client MAY reattempt 0-RTT if it receives a Retry or Version\n   Negotiation packet.  These packets do not signify rejection of 0-RTT.')], False),
        ("authentication", "From RFC 9001, compare client authentication of the server, server requests for client authentication during the handshake, and post-handshake client authentication.", [
            r("rfc9001", "Client MUST authenticate server identity; server MAY request client authentication during handshake and refuse if unable.", 'A client MUST authenticate the identity of the server.', 'A server MAY request that the client authenticate during the\n   handshake.  A server MAY refuse a connection if the client is unable\n   to authenticate when requested.'),
            r("rfc9001", "Server MUST NOT use post-handshake client authentication/CertificateRequest; client treats such messages as PROTOCOL_VIOLATION.", 'A server MUST NOT use post-handshake client authentication', 'servers MUST NOT send post-\n   handshake TLS CertificateRequest messages, and clients MUST treat\n   receipt of such messages as a connection error of type\n   PROTOCOL_VIOLATION.')], False),
        ("replay-entailment", "Why does RFC 9001's idempotent QUIC-frame processing not prove application 0-RTT is replay-safe, and what must application protocols describe?", [
            r("rfc9001", "Protocol-state frame processing is idempotent, but application information may be replay-vulnerable and TLS replay protections imperfect.", 'QUIC is not vulnerable to replay attack, except via the application\n   protocol information it might carry.', 'Processing of QUIC frames is idempotent', 'these protections are\n   imperfect.'),
            r("rfc9001", "Application protocol MUST describe 0RTT use and replay-protection measures; disabling0RTT is most effective defense.", 'protocol that uses QUIC MUST describe how the protocol uses 0-RTT and\n   the measures that are employed to protect against replay attack.', 'Disabling 0-RTT entirely is the most effective defense against replay\n   attack.')], False),
        ("missing-path-latency", "What client Initial UDP-payload minimum does RFC 9000 require, and what measured median QUIC handshake latency in milliseconds on a Shanghai-to-Beijing production path is reported by RFCs 9000/9001?", [
            r("rfc9000", "Client Initial datagrams must have UDP payload at least1200 bytes.", 'Clients MUST ensure that UDP datagrams containing Initial packets\n   have UDP payloads of at least 1200 bytes'),
            r("rfc9001", "Give measured median Shanghai-to-Beijing production handshake latency in milliseconds.", notes="Unavailable: packet-size requirements and handshake diagrams are not measurements on that path.")], True),
        ("missing-growth", "What are RFC 9000's default max_udp_payload_size and minimum-valid value, and what measured year-over-year percentage growth in production QUIC throughput do RFCs 9000/9001 disclose?", [
            r("rfc9000", "Default max_udp_payload_size is65527 bytes; values below1200 invalid.", 'default for this parameter is the maximum permitted UDP\n      payload of 65527.  Values below 1200 are invalid.'),
            r("rfc9001", "Give observed year-over-year production QUIC throughput growth percentage.", notes="Unavailable: byte limits and latency motivation cannot establish throughput growth.")], True),
    ]
    for number, (topic, query, requirements, missing) in enumerate(quic_cases, 13):
        question(f"rfc-held-{number:03d}", "held_out", "quic/" + topic,
                 ["rfc9000", "rfc9001"], query, requirements, missing)
    return questions


def build(sources: Path, target: Path) -> dict:
    target = target.resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("Fixture target must be inside the repository")
    raw, text, derived = {}, {}, {}
    for key, expected in SOURCE_HASHES.items():
        raw[key] = (sources / f"{key}.txt").read_bytes()
        if hashlib.sha256(raw[key]).hexdigest() != expected:
            raise ValueError(f"Original RFC digest mismatch: {key}")
        text[key] = raw[key].decode("utf-8")
        data = {"derivation": "Full original RFC text in one logical page-type container; not PDF/visual page parsing. No text normalization or gold selection.",
                "chunks": [{"chunk_id": key + "-fulltext", "type": "page", "content": text[key],
                            "metadata": {"page_nums": [], "full_original_sha256": expected}}]}
        derived[key] = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
    questions = inventory_questions()
    invalid_proofs = []
    for q in questions:
        for requirement in q["requirements"]:
            for proof in requirement["proofs"]:
                for quote in proof["quotes"]:
                    if quote not in text[proof["doc_key"]]:
                        invalid_proofs.append(f"{requirement['id']}: {quote!r}")
    if invalid_proofs:
        raise ValueError("Non-exact proofs: " + "; ".join(invalid_proofs))
    documents = [{"doc_key": key, "source_path": str((target / key / "chunks.json").relative_to(ROOT)),
                  "source_sha256": hashlib.sha256(derived[key]).hexdigest(), "source_file_name": f"{key.upper()}.txt",
                  "original_url": f"https://www.rfc-editor.org/rfc/{key}.txt", "original_sha256": expected}
                 for key, expected in SOURCE_HASHES.items()]
    gold = {"schema_version": "knowhere-live-gold/1",
            "scope": "New manual RFC inventory, frozen before model outputs: 6 development questions from RFC2119; 24 held-out questions from JSON (8259/7493) and QUIC (9000/9001), 12 per family. Four held-out questions deliberately request absent measurements. Full official source bytes including copyright notices are preserved. Semantic requirements and answerability are independent of the production reviewer. Known-topic public normative documents may have appeared in model training; this is unseen-in-this-experiment, not guaranteed unseen-to-model data. Text tables, conditions, comparisons, normative strength, units and related-but-non-entailing facts are covered; visual PDF/HTML-table parsing and production generalization are not tested. Literal quote recall requires all quotes in a proof; semantic correctness is separately judged.",
            "documents": documents, "questions": questions}
    target.mkdir(parents=True, exist_ok=False)
    for key in SOURCE_HASHES:
        directory = target / key
        directory.mkdir()
        (directory / f"{key}.txt").write_bytes(raw[key])
        (directory / "chunks.json").write_bytes(derived[key])
    (target / "gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n")
    return {"gold_path": str(target / "gold.json"), "gold_sha256": hashlib.sha256((target / "gold.json").read_bytes()).hexdigest(),
            "questions": len(questions), "requirements": sum(len(q["requirements"]) for q in questions),
            "split_counts": dict(Counter(q["split"] for q in questions)),
            "family_counts": dict(Counter(q["cluster_id"].split("/")[0] for q in questions)),
            "unanswerable_counts": dict(Counter(q["split"] for q in questions if q["answerability"] == "unanswerable")),
            "all_exact_proofs_verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=ROOT / "scripts/fixtures/evidence_review_rfc_20261011")
    args = parser.parse_args()
    print(json.dumps(build(args.sources, args.target), indent=2))
