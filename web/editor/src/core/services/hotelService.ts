export interface Hotel {
  id: string;
  name: string;
  rating: number;
  price: number;
  image: string;
  coordinates: {
    latitude: number;
    longitude: number;
  };
}

export interface HotelDetail extends Hotel {
  description: string;
  amenities: string[];
  reviews: number;
}

export class HotelService {
  apiKey = 'REDACTED_HOTEL_API_KEY';
  baseUrl = 'https://tripadvisor-scraper-api.omkar.cloud/tripadvisor';
  
  async searchHotels(city: string): Promise<Hotel[]> {
    const response = await fetch(
      `${this.baseUrl}/hotels/search?query=${encodeURIComponent(city)}`,
      { headers: { 'API-Key': this.apiKey } }
    );
    const data = await response.json();
    return data.results.map((item: any) => this.transformHotel(item));
  }
  
  async getHotelDetails(entityId: string): Promise<HotelDetail> {
    const response = await fetch(
      `${this.baseUrl}/hotels/detail?entity_id=${entityId}`,
      { headers: { 'API-Key': this.apiKey } }
    );
    const data = await response.json();
    return this.transformDetail(data);
  }
  
  filterByPriceRange(hotels: Hotel[], range: 'budget' | 'comfort' | 'luxury'): Hotel[] {
    const priceMap = {
      budget: { min: 0, max: 300 },
      comfort: { min: 300, max: 800 },
      luxury: { min: 800, max: Infinity }
    };
    
    return hotels.filter(h => 
      h.price >= priceMap[range].min && 
      h.price <= priceMap[range].max
    );
  }
  
  private transformHotel(item: any): Hotel {
    return {
      id: item.tripadvisor_entity_id?.toString() || '',
      name: item.name || '',
      rating: item.rating || 0,
      price: item.price || 0,
      image: item.featured_image || '',
      coordinates: {
        latitude: item.coordinates?.latitude || 0,
        longitude: item.coordinates?.longitude || 0
      }
    };
  }
  
  private transformDetail(item: any): HotelDetail {
    return {
      ...this.transformHotel(item),
      description: item.description || '',
      amenities: item.amenities || [],
      reviews: item.reviews || 0
    };
  }
}
