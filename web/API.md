# Auto_Jobs_Applier_AIHawk API Documentation

This document provides details about the RESTful API endpoints available in the Auto_Jobs_Applier_AIHawk web application.

## Authentication

The API uses JWT (JSON Web Token) authentication. To access protected endpoints, you need to include the JWT token in the Authorization header:

```
Authorization: Bearer <your_token>
```

### Authentication Endpoints

#### Login

```
POST /api/auth/login
```

Request body:

```json
{
  "email": "user@example.com",
  "password": "your_password"
}
```

Response:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "username": "username",
    "email": "user@example.com",
    "first_name": "First",
    "last_name": "Last",
    "is_admin": false
  }
}
```

#### Register

```
POST /api/auth/register
```

Request body:

```json
{
  "username": "username",
  "email": "user@example.com",
  "password": "your_password",
  "first_name": "First",
  "last_name": "Last"
}
```

Response:

```json
{
  "message": "User registered successfully",
  "user": {
    "id": 1,
    "username": "username",
    "email": "user@example.com"
  }
}
```

#### Refresh Token

```
POST /api/auth/refresh
```

Request headers:

```
Authorization: Bearer <refresh_token>
```

Response:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Logout

```
POST /api/auth/logout
```

Request headers:

```
Authorization: Bearer <access_token>
```

Response:

```json
{
  "message": "Successfully logged out"
}
```

## User Endpoints

### Get Current User

```
GET /api/user
```

Response:

```json
{
  "id": 1,
  "username": "username",
  "email": "user@example.com",
  "first_name": "First",
  "last_name": "Last",
  "full_name": "First Last",
  "is_admin": false,
  "last_login": "2023-01-01T12:00:00Z",
  "created_at": "2023-01-01T10:00:00Z",
  "subscription": {
    "plan_name": "Premium",
    "status": "active",
    "is_trial": false,
    "days_remaining": 30,
    "is_active": true
  }
}
```

### Update User

```
PATCH /api/user
```

Request body:

```json
{
  "first_name": "New First",
  "last_name": "New Last"
}
```

Response:

```json
{
  "message": "User updated successfully",
  "user": {
    "id": 1,
    "username": "username",
    "email": "user@example.com",
    "first_name": "New First",
    "last_name": "New Last",
    "full_name": "New First New Last"
  }
}
```

### Change Password

```
POST /api/user/change-password
```

Request body:

```json
{
  "current_password": "your_current_password",
  "new_password": "your_new_password"
}
```

Response:

```json
{
  "message": "Password changed successfully"
}
```

## Job Configuration Endpoints

### Get All Job Configurations

```
GET /api/job-configs
```

Response:

```json
{
  "job_configs": [
    {
      "id": 1,
      "name": "Software Engineer Jobs",
      "is_active": true,
      "is_default": true,
      "remote": true,
      "distance": 25,
      "apply_once_at_company": true,
      "experience_levels": {
        "internship": false,
        "entry": true,
        "associate": true,
        "mid-senior level": true,
        "director": false,
        "executive": false
      },
      "job_types": {
        "full-time": true,
        "contract": false,
        "part-time": false,
        "temporary": false,
        "internship": false,
        "other": false,
        "volunteer": false
      },
      "date_filters": {
        "all time": false,
        "month": false,
        "week": true,
        "24 hours": false
      },
      "searches": [
        {
          "location": "San Francisco, CA",
          "positions": ["Software Engineer", "Full Stack Developer"]
        },
        {
          "location": "Remote",
          "positions": ["Python Developer", "JavaScript Developer"]
        }
      ],
      "company_blacklist": ["Company A", "Company B"],
      "title_blacklist": ["Senior Manager", "Director"],
      "job_applicants_threshold": {
        "min_applicants": 0,
        "max_applicants": 100
      },
      "created_at": "2023-01-01T10:00:00Z",
      "updated_at": "2023-01-01T12:00:00Z"
    }
  ]
}
```

### Get a Specific Job Configuration

```
GET /api/job-configs/{config_id}
```

Response: Same as a single item in the array above.

### Create a Job Configuration

```
POST /api/job-configs
```

Request body: Same format as the response above, without the id, created_at, and updated_at fields.

### Update a Job Configuration

```
PUT /api/job-configs/{config_id}
```

Request body: Same format as the response above, without the id, created_at, and updated_at fields.

### Delete a Job Configuration

```
DELETE /api/job-configs/{config_id}
```

Response:

```json
{
  "message": "Job configuration deleted successfully"
}
```

## Resume Endpoints

### Get All Resumes

```
GET /api/resumes
```

Response:

```json
{
  "resumes": [
    {
      "id": 1,
      "name": "Software Engineer Resume",
      "description": "My main resume for software engineering positions",
      "file_type": "pdf",
      "is_default": true,
      "is_active": true,
      "created_at": "2023-01-01T10:00:00Z",
      "updated_at": "2023-01-01T12:00:00Z"
    }
  ]
}
```

### Get a Specific Resume

```
GET /api/resumes/{resume_id}
```

Response: Same as a single item in the array above.

### Download a Resume

```
GET /api/resumes/{resume_id}/download
```

Response: The resume file as an attachment.

### Upload a Resume

```
POST /api/resumes
```

Request: Multipart form data with the following fields:

- file: The resume file (PDF, DOCX, or HTML)
- name: The name of the resume
- description: (optional) A description of the resume
- is_default: (optional) Whether this is the default resume

Response: Same as a single resume item above.

### Update a Resume

```
PUT /api/resumes/{resume_id}
```

Request body:

```json
{
  "name": "Updated Resume Name",
  "description": "Updated description",
  "is_default": true
}
```

Response: Same as a single resume item above.

### Delete a Resume

```
DELETE /api/resumes/{resume_id}
```

Response:

```json
{
  "message": "Resume deleted successfully"
}
```

## Job Application Endpoints

### Get All Job Applications

```
GET /api/job-applications
```

Query parameters:

- page: Page number (default: 1)
- per_page: Items per page (default: 20)
- status: Filter by status (e.g., "applied", "interviewed", "rejected")
- company: Filter by company name
- search_term: Search in job title, company name, or location

Response:

```json
{
  "job_applications": [
    {
      "id": 1,
      "job_title": "Software Engineer",
      "company_name": "Example Company",
      "location": "San Francisco, CA",
      "application_date": "2023-01-01T10:00:00Z",
      "status": "applied",
      "job_url": "https://www.linkedin.com/jobs/view/123456789",
      "salary_range": "$100,000 - $150,000",
      "applicant_count": 50,
      "search_term": "Software Engineer",
      "search_location": "San Francisco, CA",
      "created_at": "2023-01-01T10:00:00Z",
      "updated_at": "2023-01-01T10:00:00Z"
    }
  ],
  "total": 100,
  "pages": 5,
  "page": 1,
  "per_page": 20
}
```

### Get a Specific Job Application

```
GET /api/job-applications/{application_id}
```

Response: Same as a single item in the array above, plus additional fields:

- status_updates: Array of status update objects
- questions_and_answers: Array of question and answer objects
- application_details: Object with additional details
- job_description: The full job description

### Update Job Application Status

```
PUT /api/job-applications/{application_id}/status
```

Request body:

```json
{
  "status": "interviewed",
  "notes": "Had a great interview with the team"
}
```

Response:

```json
{
  "message": "Job application status updated successfully",
  "application": {
    "id": 1,
    "job_title": "Software Engineer",
    "company_name": "Example Company",
    "location": "San Francisco, CA",
    "application_date": "2023-01-01T10:00:00Z",
    "status": "interviewed",
    "job_url": "https://www.linkedin.com/jobs/view/123456789",
    "salary_range": "$100,000 - $150,000",
    "applicant_count": 50,
    "search_term": "Software Engineer",
    "search_location": "San Francisco, CA",
    "created_at": "2023-01-01T10:00:00Z",
    "updated_at": "2023-01-01T12:00:00Z"
  }
}
```

### Get Job Application Statistics

```
GET /api/job-applications/stats
```

Response:

```json
{
  "total_applications": 100,
  "by_status": {
    "applied": 50,
    "interviewed": 20,
    "rejected": 10,
    "offered": 5,
    "accepted": 2
  },
  "top_companies": {
    "Example Company": 10,
    "Another Company": 8,
    "Third Company": 5
  },
  "top_search_terms": {
    "Software Engineer": 30,
    "Full Stack Developer": 20,
    "Python Developer": 15
  }
}
```

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request

```json
{
  "error": "Error message describing the issue"
}
```

### 401 Unauthorized

```json
{
  "error": "Invalid credentials"
}
```

### 403 Forbidden

```json
{
  "error": "You do not have permission to access this resource"
}
```

### 404 Not Found

```json
{
  "error": "Resource not found"
}
```

### 500 Internal Server Error

```json
{
  "error": "Internal server error"
}
```
