# RideMatch

A ride-matching application that efficiently pairs drivers with ride requests.

## Project Structure

- `app/` - Main application code
  - `api/` - API routes and endpoints
  - `engine/` - Core matching and queue management logic
  - `models/` - Data models
  - `services/` - Business logic services
- `tests/` - Test suite

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"  # For development
   ```

3. Run tests:
   ```bash
   pytest
   ```

## Development

Make sure to install pre-commit hooks:
```bash
pre-commit install
```
