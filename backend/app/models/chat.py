from pydantic import BaseModel
from typing import Optional, List

class ChatMessage(BaseModel):
    message: str
    
class ChatResponse(BaseModel):
    response: str

class TravelBooking(BaseModel):
    booking_id: str
    passenger_id: str
    flight_no: Optional[str] = None
    hotel_name: Optional[str] = None
    car_rental: Optional[str] = None
    excursions: List[str] = [] 