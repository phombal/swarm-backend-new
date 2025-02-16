import pytest
import asyncio
from datetime import datetime, UTC
import time
import logging
from app.database import (
    create_simulation,
    update_simulation_status,
    get_simulation_status,
    get_simulation_results,
    update_call_transcript,
    create_call_record
)
from app.services.test_runner import TestRunner

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture
def sample_scenario():
    return {
        "system_message": "You are a customer service agent for a pizza delivery service. Keep your responses brief and friendly.",
        "voice": "sage",
        "max_turns": 3,
        "conversation_flow": [
            {"role": "user", "content": "I want to order a pizza"},
            {"role": "assistant", "content": "I'll help you order a pizza. What toppings would you like?"}
        ]
    }

@pytest.fixture
def sample_transcript():
    current_time = datetime.now(UTC).isoformat()
    return [
        {
            "speaker": "user",
            "text": "Hello, I need help",
            "timestamp": current_time
        },
        {
            "speaker": "assistant",
            "text": "How can I assist you today?",
            "timestamp": current_time
        }
    ]

@pytest.fixture
async def test_simulation(sample_scenario):
    """Create a test simulation that will be used across tests."""
    simulation_id = await create_simulation(
        user_id="test_user",
        target_phone="+15597703299",
        concurrent_calls=3,
        scenario=sample_scenario
    )
    return simulation_id

@pytest.mark.asyncio
async def test_live_conversation(test_simulation, sample_scenario):
    """Test a live conversation with actual phone calls and verify the interaction."""
    logger.info("Starting live conversation test")
    
    # Create test runner with just 1 call for easier verification
    runner = TestRunner(
        simulation_id=test_simulation,
        target_phone="+15597703299",
        concurrent_calls=1,
        scenario=sample_scenario
    )
    
    try:
        # Start the simulation
        logger.info("Updating simulation status to running")
        await update_simulation_status(test_simulation, "running")
        
        # Run the simulation in the background
        logger.info("Starting simulation task")
        simulation_task = asyncio.create_task(runner.run_simulation())
        
        # Wait for a short time to let the call initialize
        logger.info("Waiting for call initialization")
        await asyncio.sleep(5)
        
        # Get initial results
        logger.info("Getting initial results")
        initial_results = await get_simulation_results(test_simulation)
        assert initial_results is not None, "Initial results should not be None"
        assert len(initial_results["calls"]) > 0, "Should have at least one call record"
        
        # Get the call_sid
        call_sid = initial_results["calls"][0]["call_sid"]
        logger.info(f"Got call_sid: {call_sid}")
        assert call_sid is not None, "Call SID should not be None"
        
        # Wait for the conversation to progress
        max_wait_time = 60  # Maximum wait time in seconds
        start_time = time.time()
        conversation_complete = False
        
        logger.info("Waiting for conversation to progress")
        while time.time() - start_time < max_wait_time and not conversation_complete:
            results = await get_simulation_results(test_simulation)
            if not results or not results["calls"]:
                logger.debug("No results yet, waiting...")
                await asyncio.sleep(2)
                continue
            
            call = results["calls"][0]
            transcript = call.get("transcript", [])
            logger.debug(f"Current transcript length: {len(transcript)}")
            
            # Log the current state
            logger.debug(f"Call status: {call.get('status')}")
            logger.debug(f"Transcript: {transcript}")
            
            # Check if we have some conversation content
            if transcript and len(transcript) >= 2:
                conversation_complete = True
                logger.info("Conversation has required content")
                break
            
            await asyncio.sleep(2)
        
        # Get final results before stopping
        final_results = await get_simulation_results(test_simulation)
        logger.info(f"Final results before stopping: {final_results}")
        
        # Stop the simulation
        logger.info("Stopping simulation")
        await runner.stop_simulation()
        
        try:
            await asyncio.wait_for(simulation_task, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Simulation task timeout, proceeding with cleanup")
        
        # Verify results
        assert conversation_complete, "Conversation did not complete within expected time"
        assert final_results is not None, "Final results should not be None"
        assert final_results["status"] in ["completed", "running", "failed"], f"Unexpected status: {final_results['status']}"
        
        final_call = final_results["calls"][0]
        assert final_call["status"] in ["completed", "in-progress", "failed"], f"Unexpected call status: {final_call['status']}"
        assert final_call.get("transcript"), "Should have conversation transcript"
        
    except Exception as e:
        logger.error(f"Error in live conversation test: {str(e)}", exc_info=True)
        await update_simulation_status(test_simulation, "failed", str(e))
        raise
    finally:
        # Ensure simulation is stopped
        try:
            await runner.stop_simulation()
        except Exception as e:
            logger.error(f"Error stopping simulation: {str(e)}")

async def test_simulation_creation(test_simulation):
    """Test creating a new simulation."""
    # Verify simulation was created
    assert test_simulation is not None
    
    # Get simulation status
    status = await get_simulation_status(test_simulation)
    assert status is not None
    assert status["status"] == "initiated"
    assert status["concurrent_calls"] == 3

async def test_simulation_lifecycle(test_simulation, sample_transcript):
    """Test the complete lifecycle of a simulation with call transcripts."""
    # Create a call record
    call_sid = "test_call_1"
    await create_call_record(test_simulation, call_sid)
    
    # Update simulation status to running
    await update_simulation_status(test_simulation, "running")
    status = await get_simulation_status(test_simulation)
    assert status["status"] == "running"
    
    # Update call transcript
    await update_call_transcript(test_simulation, call_sid, sample_transcript)
    
    # Complete simulation
    await update_simulation_status(test_simulation, "completed")
    
    # Get final results
    results = await get_simulation_results(test_simulation)
    assert results is not None
    assert results["status"] == "completed"
    assert len(results["calls"]) > 0
    assert results["calls"][0]["transcript"] == sample_transcript

async def test_error_handling(test_simulation):
    """Test error handling in simulation operations."""
    # Update with error
    error_message = "Test error message"
    await update_simulation_status(test_simulation, "failed", error_message)
    
    # Verify error was recorded
    status = await get_simulation_status(test_simulation)
    assert status["status"] == "failed"
    assert status["error"] == error_message

async def test_concurrent_calls(test_simulation):
    """Test handling multiple concurrent calls in a simulation."""
    # Create multiple call records
    call_sids = []
    for i in range(3):
        call_sid = f"test_call_{i}"
        await create_call_record(test_simulation, call_sid)
        call_sids.append(call_sid)
    
    # Get results and verify call count
    results = await get_simulation_results(test_simulation)
    assert len(results["calls"]) == 3
    
    # Verify all call_sids are present
    result_call_sids = [call["call_sid"] for call in results["calls"]]
    assert all(sid in result_call_sids for sid in call_sids)

if __name__ == "__main__":
    # Run tests
    asyncio.run(test_simulation_creation(test_simulation()))
    asyncio.run(test_simulation_lifecycle(test_simulation(), sample_transcript()))
    asyncio.run(test_error_handling(test_simulation()))
    asyncio.run(test_concurrent_calls(test_simulation()))
    asyncio.run(test_live_conversation(test_simulation(), sample_scenario())) 