import pytest
import asyncio
from app.database import supabase_client

# Mark all tests as async
def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.asyncio)

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def setup_database():
    """Setup and cleanup the test database before and after each test."""
    try:
        # Clean up any existing test data
        # First delete call records for test simulations
        test_simulations = supabase_client.table("simulations").select("id").eq("user_id", "test_user").execute()
        if test_simulations.data:
            for sim in test_simulations.data:
                supabase_client.table("call_records").delete().eq("simulation_id", sim["id"]).execute()
        
        # Then delete test simulations
        supabase_client.table("simulations").delete().eq("user_id", "test_user").execute()
        
        yield
        
        # Clean up after the test
        # First delete call records for test simulations
        test_simulations = supabase_client.table("simulations").select("id").eq("user_id", "test_user").execute()
        if test_simulations.data:
            for sim in test_simulations.data:
                supabase_client.table("call_records").delete().eq("simulation_id", sim["id"]).execute()
        
        # Then delete test simulations
        supabase_client.table("simulations").delete().eq("user_id", "test_user").execute()
    
    except Exception as e:
        print(f"Error in database cleanup: {str(e)}")
        raise 