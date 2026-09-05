# Project name : 
Thailand Coastal Sports Dashboard

# description :
A real-time weather and marine data pipeline + interactive Streamlit dashboard for water-sports coast line in Thailand. Weather data is fetched from Open-Meteo, and displayed on an interactive map with per-sport condition scoring.

# features :
- Interactive map : of Thailand coastal line with markers for best tourism spots with weather condition and best suited water sport for the spot.   
- A weather dashboard for each spot including :
    - 7 days weather forecast
    - For each weather condition the range of optimal condition for the water sport depending on the weather, such as: Wind for Kitesurf, and wave height for Surfing.
- Best location and time for each water sport from all the spots for the next 7 days.
- User can chose wind units (knots, km/h, m/s, mph) and wave height units (meters, feet).

# data sources :
- Weather data: Open-Meteo Weather and Marine APIs.

# Sport thresholds:
Optimal range of conditions and weights (Those thresholds and weights where chosen by me arbitrarily):
- Kitesurf
    - Wind speed: 12-30 knots, 70%
    - Wave height: 0-1 meters, 20%
    - precipitation: 0-10 mm, 10%
- Surfing
    - Wind speed: 5-20 knots, 10%
    - Wave height: 1-3 meters, 80%
    - precipitation: 0-10 mm, 10%
- SUP
    - Wind speed: 0-10 knots, 20%
    - Wave height: 0-0.5 meters, 50%
    - precipitation: 0-10 mm, 30%

# Rating System:
    - The rating system should be based on a weighted average of the optimal conditions for each sport : 
        rating = sum(weight * ( 1 - ( max(0, min_range - condition, condition - max_range)) / (max_range - min_range))) 

    - Extreme condition should automaticly get a score of 0:
        -Kitesurf:
            -wind > 40 knots
            -wave height > 4 meters
            -precipitation > 20 mm
        -Surfing:
            -wind > 25 knots
            -wave height > 6 meters
            -precipitation > 20 mm
        -SUP:
            -wind > 20 knots
            -wave height > 2 meters
            -precipitation > 20 mm
    
    - Grade rating:
      Score , Label , Colour
      76–100 , Optimal , Green
      51–75 , Good , Light green
      26–50 , Caution , Yellow
      0–25 , Dangerous , Red

# Locations:
 Location , Region , Lat , Lon ,
 Koh Phangan - Ban Tai (South) , Gulf of Thailand , 9.7022 , 100.0245 ,
 Koh Phangan - Chaloklum (North) , Gulf of Thailand , 9.7891 , 100.0075 ,
 Koh Phangan - Haad Yao / Sri Thanu (West) , Gulf of Thailand , 9.7620 , 99.9620 ,
 Koh Phangan - Thong Nai Pan (East) , Gulf of Thailand , 9.7745 , 100.0550 ,
 Hua Hin - Pranburi , Gulf of Thailand , 12.5684 , 99.9577 ,
 Koh Samui - Chaweng , Gulf of Thailand , 9.5300 , 100.0650 ,
 Koh Samui - Lipa Noi , Gulf of Thailand , 9.5100 , 99.9330 ,
 Phuket - Kata Beach , Andaman Sea , 7.8206 , 98.2987 ,
 Phuket - Nai Harn , Andaman Sea , 7.7770 , 98.3060 ,
 Phuket - Nai Yang , Andaman Sea , 8.0930 , 98.2965 ,
 Krabi - Railay , Andaman Sea , 8.0120 , 98.8375 


# Project structure:
- README.md
- requirements.txt
- app.py                  # Streamlit application
- etl.py                  # Main ETL / data processing entry point
- /data/raw/              # Raw API extracts or cached raw data
- /data/processed/        # Processed analytical outputs
- /ai_transcript/         # Full AI conversation transcript
- /src/                   # Optional supporting code/modules
- /tests/                 # Optional tests


# Data process:
 - Data range validation: check for outliers and anomalies due to 
   unit differences or data corruption, and remove any problematic dates.
 - Filter out time frame not in the range 05:00 - 19:00 for each day.
 - Optional unit change according to user`s choise in the dashboard.
 - Combine both API to one table.

 # Dashboard:
    - Main page: Map of Thailand with markers for each location. 
      Colors for the markers should be based on the best water sport for the location.
    - Second screen: Time series for each weather condition for a selected location. 
    - Third screen: Best location and time for each water sport from all the spots for the next 7 days.

