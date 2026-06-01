import httpx
import asyncio
import json
import uuid
import time

async def test():
    async with httpx.AsyncClient() as client:
        # Create a driver
        driver_data = {
            'driver_name': 'Test Driver',
            'rating': 4.8,
            'lat': 40.7128,
            'lng': -74.0060,
            'max_capacity': 4
        }
        driver_response = await client.post('http://127.0.0.1:8000/api/v1/drivers/', json=driver_data)
        print('Driver created:', driver_response.status_code)
        if driver_response.status_code != 201:
            print('Error:', driver_response.text)
            print('Full response:', driver_response.content)
            return
        driver_id = driver_response.json()['id']
        print('Driver ID:', driver_id)
        
        # Create a ride request
        ride_data = {
            'rider_id': str(uuid.uuid4()),
            'pickup_lat': 40.7180,
            'pickup_lng': -74.0020,
            'dropoff_lat': 40.7580,
            'dropoff_lng': -73.9855,
            'priority': 'NORMAL'
        }
        ride_response = await client.post('http://127.0.0.1:8000/api/v1/rides/', json=ride_data)
        print('Ride created:', ride_response.status_code)
        if ride_response.status_code != 201:
            print('Error:', ride_response.text)
            return
        ride = ride_response.json()
        print('Ride ID:', ride['id'])
        
        # Check event bus metrics
        time.sleep(2)  # Wait for event to be processed
        
        metrics_response = await client.get('http://127.0.0.1:8000/api/v1/events/metrics')
        metrics = metrics_response.json()
        print('\nEvent bus metrics:')
        print('Published:', metrics['metrics']['events_published'])
        print('Processed:', metrics['metrics']['events_processed'])
        print('Queue size:', metrics['queue_size'])
        print('Running:', metrics['is_running'])

asyncio.run(test())


