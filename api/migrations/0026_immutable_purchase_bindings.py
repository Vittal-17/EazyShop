from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('api', '0025_purchase_intents')]
    operations = [migrations.RunSQL(
        sql="""
        CREATE FUNCTION eazyshop_immutable_purchase_terms() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF ROW(NEW.purpose, NEW.purchaser_id, NEW.order_id, NEW.currency, NEW.expected_amount,
                 NEW.wallet_amount, NEW.wallet_debit_id, NEW.idempotency_key)
             IS DISTINCT FROM
             ROW(OLD.purpose, OLD.purchaser_id, OLD.order_id, OLD.currency, OLD.expected_amount,
                 OLD.wallet_amount, OLD.wallet_debit_id, OLD.idempotency_key)
             OR (OLD.provider_order_id IS NOT NULL AND NEW.provider_order_id IS DISTINCT FROM OLD.provider_order_id)
             OR (OLD.gift_card_id IS NOT NULL AND NEW.gift_card_id IS DISTINCT FROM OLD.gift_card_id)
             OR (OLD.state IN ('cancelled', 'failed', 'refunded', 'reconciliation') AND NEW.state IN ('pending', 'settled'))
          THEN RAISE EXCEPTION 'Immutable purchase binding or closed state' USING ERRCODE = '23514'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER immutable_purchase_terms BEFORE UPDATE ON api_purchaseintent
          FOR EACH ROW EXECUTE FUNCTION eazyshop_immutable_purchase_terms();
        CREATE FUNCTION eazyshop_immutable_payment_claim() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF ROW(NEW.payment_id, NEW.intent_id, NEW.provider_order_id, NEW.amount, NEW.currency)
             IS DISTINCT FROM ROW(OLD.payment_id, OLD.intent_id, OLD.provider_order_id, OLD.amount, OLD.currency)
             OR (OLD.state IN ('refunded', 'quarantined', 'refund_pending') AND NEW.state = 'captured')
          THEN RAISE EXCEPTION 'Immutable payment claim' USING ERRCODE = '23514'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER immutable_payment_claim BEFORE UPDATE ON api_providerpaymentclaim
          FOR EACH ROW EXECUTE FUNCTION eazyshop_immutable_payment_claim();
        """,
        reverse_sql="""
        DROP TRIGGER immutable_payment_claim ON api_providerpaymentclaim;
        DROP FUNCTION eazyshop_immutable_payment_claim();
        DROP TRIGGER immutable_purchase_terms ON api_purchaseintent;
        DROP FUNCTION eazyshop_immutable_purchase_terms();
        """,
    )]
