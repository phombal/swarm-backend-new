import pytest
import asyncio
from datetime import datetime, UTC
from app.database import (
    create_simulation,
    update_simulation_status,
    get_simulation_status,
    get_simulation_results,
    update_call_transcript,
    create_call_record
)

@pytest.fixture
def sample_scenario():
    return {
        "voice": "sage",
        "system_message": "You are a customer service agent",
        "max_turns": 5,
        "conversation_flow": [
            {"role": "user", "content": "I need help with my order"},
            {"role": "assistant", "content": "I'll be happy to help you with that"}
        ]
    }

@pytest.fixture
def sample_transcript():
    return [
        {"timestamp": datetime.now(UTC).isoformat(), "speaker": "user", "text": "Hello, I need help"},
        {"timestamp": datetime.now(UTC).isoformat(), "speaker": "assistant", "text": "How can I assist you today?"}
    ]

async def test_simulation_creation(sample_scenario):
    """Test creating a new simulation."""
    # Create simulation
    simulation_id = await create_simulation(
        user_id="test_user",
        target_phone="+1234567890",
        concurrent_calls=2,
        scenario=sample_scenario
    )
    
    # Verify simulation was created
    status = await get_simulation_status(simulation_id)
    assert status is not None
    assert status["status"] == "initiated"
    assert status["concurrent_calls"] == 2
    assert status["scenario"] == sample_scenario

async def test_simulation_lifecycle(sample_scenario, sample_transcript):
    """Test the complete lifecycle of a simulation with call transcripts."""
    # Create simulation
    simulation_id = await create_simulation(
        user_id="test_user",
        target_phone="+1234567890",
        concurrent_calls=1,
        scenario=sample_scenario
    )
    
    # Update status to running
    await update_simulation_status(simulation_id, "running")
    status = await get_simulation_status(simulation_id)
    assert status["status"] == "running"
    
    # Create call record and update transcript
    call_sid = "test_call_123"
    await create_call_record(simulation_id, call_sid)
    await update_call_transcript(simulation_id, call_sid, sample_transcript)
    
    # Update status to completed
    await update_simulation_status(simulation_id, "completed")
    
    # Get final results
    results = await get_simulation_results(simulation_id)
    assert results is not None
    assert results["status"] == "completed"
    assert len(results["calls"]) > 0
    
    # Verify transcript
    call_record = next((call for call in results["calls"] if call["call_sid"] == call_sid), None)
    assert call_record is not None
    assert call_record["transcript"] == sample_transcript

async def test_error_handling(sample_scenario):
    """Test error handling in simulation operations."""
    # Create simulation
    simulation_id = await create_simulation(
        user_id="test_user",
        target_phone="+1234567890",
        concurrent_calls=1,
        scenario=sample_scenario
    )
    
    # Test error status update
    error_message = "Test error occurred"
    await update_simulation_status(simulation_id, "failed", error=error_message)
    
    status = await get_simulation_status(simulation_id)
    assert status["status"] == "failed"
    assert status["error"] == error_message
    assert status["end_time"] is not None

async def test_concurrent_calls(sample_scenario):
    """Test handling multiple concurrent calls in a simulation."""
    # Create simulation with multiple concurrent calls
    simulation_id = await create_simulation(
        user_id="test_user",
        target_phone="+1234567890",
        concurrent_calls=3,
        scenario=sample_scenario
    )
    
    # Simulate multiple call transcripts
    call_sids = ["call_1", "call_2", "call_3"]
    for call_sid in call_sids:
        # Create call record first
        await create_call_record(simulation_id, call_sid)
        
        transcript = [
            {"timestamp": datetime.now(UTC).isoformat(), "speaker": "user", "text": f"Hello from {call_sid}"},
            {"timestamp": datetime.now(UTC).isoformat(), "speaker": "assistant", "text": f"Hello to {call_sid}"}
        ]
        await update_call_transcript(simulation_id, call_sid, transcript)
    
    # Verify all call records
    results = await get_simulation_results(simulation_id)
    assert len(results["calls"]) == 3
    
    # Verify each call has its unique transcript
    for call_sid in call_sids:
        call = next((c for c in results["calls"] if c["call_sid"] == call_sid), None)
        assert call is not None
        assert len(call["transcript"]) == 2
        assert call_sid in call["transcript"][0]["text"]

if __name__ == "__main__":
    # Run tests
    asyncio.run(test_simulation_creation(sample_scenario()))
    asyncio.run(test_simulation_lifecycle(sample_scenario(), sample_transcript()))
    asyncio.run(test_error_handling(sample_scenario()))
    asyncio.run(test_concurrent_calls(sample_scenario())) 