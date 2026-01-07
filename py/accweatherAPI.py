import requests
from typing import Dict, Union, Optional, List

class AccuWeatherAPI:
    def __init__(self, api_key: str):
        """
        初始化AccuWeather API封装类
        
        :param api_key: AccuWeather API密钥
        """
        self.api_key = api_key
        self.base_url = "http://dataservice.accuweather.com"
        
    def get_location_info(self, city_name: str) -> Optional[List[Dict]]:
        """
        根据城市名称获取详细位置信息(包括location key)
        
        :param city_name: 城市名称
        :return: 位置信息列表(可能包含多个匹配结果)或None(如果查询失败)
        """
        url = f"{self.base_url}/locations/v1/cities/search"
        params = {
            "apikey": self.api_key,
            "q": city_name,
            "language": "zh-cn",
            "details": "true"
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data and isinstance(data, list):
                # 简化返回的数据结构，只保留关键信息
                simplified_results = []
                for location in data:
                    simplified = {
                        "key": location.get("Key"),
                        "name": location.get("LocalizedName"),
                        "english_name": location.get("EnglishName"),
                        "type": location.get("Type"),
                        "country": location.get("Country", {}).get("LocalizedName"),
                        "administrative_area": location.get("AdministrativeArea", {}).get("LocalizedName"),
                        "geo_position": {
                            "latitude": location.get("GeoPosition", {}).get("Latitude"),
                            "longitude": location.get("GeoPosition", {}).get("Longitude")
                        },
                        "time_zone": location.get("TimeZone", {}).get("Name"),
                        "primary_location": location.get("PrimaryLocation")
                    }
                    simplified_results.append(simplified)
                return simplified_results
            return None
        except requests.exceptions.RequestException as e:
            print(f"获取位置信息失败: {e}")
            return None
    
    def _get_location_key(self, city_name: str) -> Optional[str]:
        """
        根据城市名称获取location key(内部使用)
        
        :param city_name: 城市名称
        :return: location key或None(如果未找到)
        """
        location_info = self.get_location_info(city_name)
        if location_info and len(location_info) > 0:
            return location_info[0].get("key")
        return None
    
    def get_current_conditions(self, city_name: str, details: bool = True) -> Optional[Dict]:
        """
        获取实时天气情况
        
        :param city_name: 城市名称
        :param details: 是否获取详细信息
        :return: 实时天气数据字典或None(如果查询失败)
        """
        location_key = self._get_location_key(city_name)
        if not location_key:
            return None
            
        url = f"{self.base_url}/currentconditions/v1/{location_key}"
        params = {
            "apikey": self.api_key,
            "language": "zh-cn",
            "details": str(details).lower()
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data and isinstance(data, list):
                return data[0]
            return None
        except requests.exceptions.RequestException as e:
            print(f"获取实时天气失败: {e}")
            return None
    
    def get_forecast(self, city_name: str, days: int = 1, metric: bool = True, details: bool = True) -> Optional[Dict]:
        """
        获取天气预报
        
        :param city_name: 城市名称
        :param days: 预报天数(1或5)
        :param metric: 是否使用公制单位
        :param details: 是否获取详细信息
        :return: 天气预报数据字典或None(如果查询失败)
        """
        if days not in (1, 5):
            raise ValueError("days参数只能是1或5")
            
        location_key = self._get_location_key(city_name)
        if not location_key:
            return None
            
        endpoint = "daily/1day" if days == 1 else "daily/5day"
        url = f"{self.base_url}/forecasts/v1/{endpoint}/{location_key}"
        params = {
            "apikey": self.api_key,
            "language": "zh-cn",
            "metric": str(metric).lower(),
            "details": str(details).lower()
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"获取天气预报失败: {e}")
            return None
    
    def get_weather(self, city_name: str, forecast: bool = False, days: int = 1) -> Dict[str, Union[Dict, str]]:
        """
        获取天气信息(实时或预报)
        
        :param city_name: 城市名称
        :param forecast: 是否获取预报(False则获取实时天气)
        :param days: 预报天数(1或5，仅在forecast=True时有效)
        :return: 包含天气数据和状态的字典
        """
        result = {"status": "success", "data": None, "message": ""}
        
        if forecast:
            data = self.get_forecast(city_name, days)
            if not data:
                result.update({
                    "status": "error",
                    "message": f"无法获取{city_name}的{days}天天气预报"
                })
            else:
                result["data"] = data
        else:
            data = self.get_current_conditions(city_name)
            if not data:
                result.update({
                    "status": "error",
                    "message": f"无法获取{city_name}的实时天气"
                })
            else:
                result["data"] = data
        
        return result