class LiveOrderStateMachine:
    VALID_TRANSITIONS = {
        "CREATED": ["EXECUTING"],
        "EXECUTING": [
            "BROKER_ACCEPTED",
            "FAILED",
            "RECONCILING"
        ],
        "BROKER_ACCEPTED": [
            "PARTIALLY_FILLED",
            "FILLED",
            "REJECTED",
            "CANCEL_PENDING",
            "MODIFY_PENDING"
        ],
        "PARTIALLY_FILLED": [
            "FILLED",
            "PARTIALLY_FILLED",  # Allow partial fill -> partial fill updates
            "CANCEL_PENDING",
            "EXPIRED"
        ],
        "FILLED": [],  # Terminal
        "CANCEL_PENDING": [
            "CANCELLED",
            "PARTIALLY_FILLED", # Late webhook while cancelling
            "FILLED" # Late webhook filling remainder while cancelling
        ],
        "MODIFY_PENDING": [
            "BROKER_ACCEPTED", # Success/Failure reverts to base active state
            "PARTIALLY_FILLED"
        ],
        "CANCELLED": [
            "PARTIALLY_FILLED", # Exchange supremacy late fill
            "FILLED"
        ],
        "REJECTED": [],  # Terminal
        "EXPIRED": [
            "PARTIALLY_FILLED", # Late webhook
            "FILLED"
        ],
        "FAILED": [],  # Terminal
        "RECONCILING": [
            "BROKER_ACCEPTED",
            "FAILED",
            "MANUAL_INTERVENTION_REQUIRED"
        ],
        "MANUAL_INTERVENTION_REQUIRED": []  # Terminal for automation
    }

    TERMINAL_STATES = {
        "FILLED", "CANCELLED", "REJECTED", "EXPIRED", "FAILED", "MANUAL_INTERVENTION_REQUIRED"
    }

    @classmethod
    def validate_transition(cls, current_state: str, new_state: str) -> bool:
        if current_state == new_state and current_state != "PARTIALLY_FILLED":
            return True
            
        allowed = cls.VALID_TRANSITIONS.get(current_state, [])
        if new_state in allowed:
            return True
            
        raise ValueError(f"Illegal transition from {current_state} to {new_state}")

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return state in cls.TERMINAL_STATES

    @classmethod
    async def transition_order_state(
        cls, 
        db, 
        order, 
        new_state: str, 
        reason: str | None = None,
        metadata: dict | None = None,
        correlation_id: str | None = None,
        created_by: str | None = None
    ):
        """
        Atomically transitions an order state and generates an OrderExecutionEvent.
        Requires a live database session.
        """
        from ..models.live_trading import OrderExecutionEvent
        import logging
        from datetime import datetime, timezone
        
        logger = logging.getLogger(__name__)

        # 1. Validate transition
        current_state = order.status
        cls.validate_transition(current_state, new_state)

        # 2. Short-circuit idempotent same-state transitions to prevent audit pollution
        if current_state == new_state and current_state != "PARTIALLY_FILLED":
            logger.info(
                f"Order {order.id} idempotent state transition detected ({current_state}). "
                f"Short-circuiting."
            )
            return order

        # 3. Apply transition
        order.status = new_state
        
        # 4. Persist OrderExecutionEvent
        event = OrderExecutionEvent(
            order_id=order.id,
            event_type="STATE_TRANSITION",
            previous_state=current_state,
            new_state=new_state,
            reason=reason,
            metadata_json=metadata,
            correlation_id=correlation_id,
            created_by=created_by,
            event_timestamp=datetime.now(timezone.utc)
        )
        db.add(event)
        
        # 5. Commit atomically
        await db.commit()
        await db.refresh(order)
        
        logger.info(
            f"Order {order.id} transitioned {current_state} -> {new_state}. "
            f"Event recorded."
        )
        return order
