# Workflows

## Common workflow contract
Each workflow should define:
- `intent`
- `required_fields`
- `optional_fields`
- `field_priority`
- `validators`
- `conditional_requirements`
- `action`
- `escalation_conditions`

## 1. Password Reset
Intent: `password_reset`

Required fields:
- `account_id`
- `verification_code`

Action:
- `reset_password_tool`

Escalate when:
- too many invalid verification attempts
- no verified contact method available
- user requests human

## 2. Billing Dispute
Intent: `billing_dispute`

Required fields:
- `account_number`
- `charge_date`
- `charge_amount`
- `dispute_reason`

Action:
- `open_dispute_case`
