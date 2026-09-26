import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = "https://vkshop.onrender.com/api";
  static String? userToken;

  static Map<String, String> get headers => {
        "Content-Type": "application/json",
        "Accept": "application/json",
        if (userToken != null) "Authorization": "Bearer $userToken",
      };

  static Future<Map<String, dynamic>> getProducts({int page = 1, String search = '', int? categoryId}) async {
    try {
      final uri = Uri.parse("$baseUrl/products?page=$page&q=$search${categoryId != null ? '&category_id=$categoryId' : ''}");
      final response = await http.get(uri, headers: headers).timeout(const Duration(seconds: 10));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      print("API getProducts Error: $e");
    }
    return {"success": false, "products": []};
  }

  static Future<Map<String, dynamic>> getProductDetail(int productId) async {
    try {
      final response = await http.get(Uri.parse("$baseUrl/products/$productId"), headers: headers);
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      print("API getProductDetail Error: $e");
    }
    return {"success": false};
  }

  static Future<List<dynamic>> getCategories() async {
    try {
      final response = await http.get(Uri.parse("$baseUrl/categories"), headers: headers);
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return data["categories"] ?? [];
      }
    } catch (e) {
      print("API getCategories Error: $e");
    }
    return [];
  }

  static Future<Map<String, dynamic>> toggleWishlist(int productId) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/wishlist/toggle/$productId"),
        headers: headers,
      );
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      print("API toggleWishlist Error: $e");
    }
    return {"success": false};
  }

  static Future<String?> getPresignedUploadUrl(String filename, String category) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/storage/presigned-upload"),
        headers: headers,
        body: json.encode({"filename": filename, "category": category}),
      );
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return data["object_key"];
      }
    } catch (e) {
      print("API Presigned Upload Error: $e");
    }
    return null;
  }
}
