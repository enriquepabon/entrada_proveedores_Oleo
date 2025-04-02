import pytest
from app import create_app

def test_app_creation_and_homepage():
    """
    Test if the Flask application can be created and the homepage (/) responds.
    """
    # Create the Flask app instance configured for testing
    # You might need to adjust the config if you have a specific test config
    app = create_app({'TESTING': True}) 
    
    # Create a test client using the Flask application context
    with app.test_client() as client:
        # Make a GET request to the homepage, following redirects
        response = client.get('/', follow_redirects=True)
        
        # Assert that the response status code is 200 (OK)
        assert response.status_code == 200
        # Optionally, check for some content on the homepage
        # assert b"Welcome" in response.data # Example content check 