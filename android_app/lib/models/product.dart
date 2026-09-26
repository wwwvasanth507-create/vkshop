class Product {
  final int id;
  final String name;
  final String slug;
  final double basePrice;
  final double offerPrice;
  final double discountPercent;
  final String imageUrl;
  final double rating;
  final bool inStock;

  Product({
    required this.id,
    required this.name,
    required this.slug,
    required this.basePrice,
    required this.offerPrice,
    required this.discountPercent,
    required this.imageUrl,
    required this.rating,
    required this.inStock,
  });

  factory Product.fromJson(Map<String, dynamic> json) {
    return Product(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      slug: json['slug'] ?? '',
      basePrice: (json['base_price'] ?? 0.0).toDouble(),
      offerPrice: (json['offer_price'] ?? 0.0).toDouble(),
      discountPercent: (json['discount_percent'] ?? 0.0).toDouble(),
      imageUrl: json['image_url'] ?? '',
      rating: (json['rating'] ?? 0.0).toDouble(),
      inStock: json['in_stock'] ?? true,
    );
  }
}
