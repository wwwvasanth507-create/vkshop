# Commission Reject Fix

## What was actually broken

The Accept/Reject flow, permissions, exact rejection message, notification,
and history-storage were **already implemented correctly** in the uploaded
build — I verified this by driving the routes directly (login as a sub-admin,
POST to `/admin/commission/reject/<id>`, inspect the resulting rows). Both
admins and sub-admins already pass the blueprint's `check_admin_role` check,
so both roles could already reach the route.

The real bug was in `routes/admin.py`, in `reject_commission_payment()`:

```python
else:
    # Reset store commission request status
    store.commission_payment_status = 'Paid'   # <-- BUG
    store.commission_requested_at = None
```

When a **pending** (not-yet-approved) commission payment was rejected, the
seller's store was incorrectly flipped to `commission_payment_status =
'Paid'` — the opposite of what a rejection should do. This silently broke
the seller-facing side of the flow: the seller's dashboard would treat the
commission as paid even though it had just been rejected, the seller
wouldn't be prompted to resubmit, and `commission_requested_at` was cleared.
The `CommissionPayment` row itself did say `Rejected`, but the store's
overall state contradicted it — which is what made the feature look "not
working" in practice even though the button technically submitted.

**Fix:** both branches (payment was already marked Paid, or was still
pending) now correctly set `commission_payment_status = 'Requested'` and
stamp `commission_requested_at`, so the seller is properly asked to
resubmit. If the payment had already been marked Paid, the amount is also
restored to `commission_carryover_amount` as an outstanding due (this part
was already correct).

I also added an explicit role check at the top of the route (defense in
depth — the blueprint-level check already covers this, but the action
changes seller money state, so it's checked again directly) and hardened
`templates/admin/dashboard.html`: the seller-info JS data block was
building `rating` / `balance` / `total_sales` / `commission_percentage`
from raw Jinja output instead of `|tojson`. If any seller ever has a
`None` in one of those fields, the raw output would render the literal
token `None`, which is invalid JavaScript — and because it's all one
`<script>` block, that single bad value breaks the whole block, silently
disabling *every* button wired up in it, including Reject. Switched those
four fields to `|default(0, true)|tojson` so a stray `None` can't take
down the page's JS anymore.

## Confirmed after the fix (via direct route testing, not guesswork)
- Sub-admin can reject a pending commission payment.
- `CommissionPayment.status` → `Rejected`.
- `rejected_reason`, `rejected_at`, `rejected_by` stored (rejection history).
- Seller gets a notification with the exact required message.
- Store status correctly goes back to `Requested` (not `Paid`) so the
  seller is prompted to resubmit.
- Dashboard's inline script parses cleanly (checked with `node --check`).

## Files changed
- `routes/admin.py` — fixed `reject_commission_payment()`
- `templates/admin/dashboard.html` — hardened seller-data JS block
