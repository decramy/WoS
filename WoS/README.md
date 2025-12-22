# WoS - WSJF on Steroids

## Overview
WoS is a web application designed to help teams manage their backlog of work items, specifically focusing on 'epics' and 'stories'. The application provides a user-friendly interface to create, view, and manage these work items, facilitating better prioritization and planning.

## Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd WoS
   ```

2. **Create a Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Requirements**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run Migrations**
   ```bash
   python manage.py migrate
   ```

5. **Run the Development Server**
   ```bash
   python manage.py runserver
   ```

6. **Access the Application**
   Open your web browser and go to `http://127.0.0.1:8000/`.

## Features
- Create and manage epics and stories.
- User-friendly interface for backlog management.
- SQLite database for lightweight data storage.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.