# **Prescriptive ESG Engine** 

MVP ARCHITECTURE

### 1\. DEVELOPMENT WORKFLOW

Product Owner  
    ↓  
Product Backlog / Issues  
    ↓  
Scrum Master  
    ↓  
Developers  
    ↓  
Cursor / AI Development Tools  
    ↓  
GitHub Repository  
    ↓  
Pull Request / Code Review  
    ↓  
Main Branch  
    ↓  
Automatic Deployment

### 2\. APPLICATION INFRASTRUCTURE

GitHub Repository  
    ↓  
Vercel  
    ↓  
Web Application

### 3\. WEB APPLICATION

Web Application  
    ├── UI / Frontend  
    │   ├── Carbon Dashboard  
    │   ├── Emissions Overview  
    │   ├── Recommendations  
    │   ├── Scenario Analysis  
    │   ├── Reports  
    │   └── Data Upload  
    │  
    └── Application Logic  
        ├── Data Ingestion  
        ├── Transaction Classification  
        ├── Emissions Calculation  
        ├── Recommendation Engine  
        └── Reporting

### 4\. DATA INGESTION

Data Sources  
    ├── Structured CSV Data  
    │       ↓  
    │   Rule-based / Regex Processing  
    │  
    └── Unstructured Free-text Input  
            ↓  
        NLP Processing

Both sources  
    ↓  
Normalized Data  
    ↓  
Transaction Classification

### 

### 5\. TRANSACTION CLASSIFICATION

Normalized Transaction  
    ↓  
Merchant Directory  
    \+  
Rule-based / Regex Classification  
    ↓  
Transaction Category  
    ↓  
Scope 3 Category 6 or 7

### 6\. EMISSIONS CALCULATION

Classified Activity Data  
    ↓  
Emission Factors  
    ↓  
Scope 3 Emissions  
    ↓  
CO₂e Calculation

### 

### 

### 

### 

### 7\. RECOMMENDATION ENGINE

Emissions \+ Cost Data  
    ↓  
Rule-based Recommendation Playbook  
    ↓  
5–10 Abatement Measures  
    ↓  
Department / Category-level Recommendations  
    ↓  
Expected CO₂e Reduction  
    \+  
Expected Financial Impact  
    ↓  
MACC Prioritization

### 8\. DATABASE & AUTHENTICATION

Supabase  
    ├── Authentication  
    └── Database  
        ├── Demo Company  
        ├── Employees  
        ├── Departments  
        ├── Transactions  
        ├── Travel Data  
        ├── Emissions Data  
        └── Recommendations  
