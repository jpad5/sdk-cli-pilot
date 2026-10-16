# Synthetic workshop fixtures

**Every person, company, relationship, allegation and list entry here is invented.**
No record describes a real customer or actual sanctions, political exposure or adverse media.
Real ISO country codes are used only to exercise workshop jurisdiction rules. The lists are not official sources. Do not use these fixtures for real compliance decisions.

- `customers.json`: eight records validated against `kyc_core.models.CustomerProfile`.
- `sanctions.csv`: twenty fictional entries; aliases are separated by `;`.
- `llm_responses.json`: decision-keyed assistant templates; `{customer_name}` is the substitution field (the unknown reply has no fields).

| ID | Scenario |
| --- | --- |
| CUST-1001 | Clean, low-risk individual |
| CUST-1002 | Exact PEP match |
| CUST-1003 | Exact sanctions match |
| CUST-1004 | Sanctions alias match |
| CUST-1005 | Near-miss control: Quillhaven Robotics is not Quillhaven Minerals |
| CUST-1006 | High-risk jurisdiction and large cash volume |
| CUST-1007 | Shell-like entity: opaque ownership and third-party transfers |
| CUST-1008 | Adverse-media match |

Settings resolve these files from `shared\mock`; override with `KYC_MOCK_DIR`.
