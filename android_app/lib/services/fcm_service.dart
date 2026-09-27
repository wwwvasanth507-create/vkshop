import 'package:flutter/foundation.dart';
import 'api_service.dart';

/// VKShop Firebase Cloud Messaging Service Helper
/// Handles notification permissions, FCM token registration,
/// token refresh listener, and notification tap navigation.
class FCMNotificationService {
  static String? currentDeviceId;
  static String? currentFcmToken;

  /// Initialize Firebase Messaging & Register Token with Backend
  static Future<void> initialize({
    required String deviceId,
    required String platform,
    String? deviceName,
    String? appVersion,
    Function(Map<String, dynamic> data)? onNotificationTap,
  }) async {
    currentDeviceId = deviceId;
    debugPrint("Initializing FCM Service for Device ID: $deviceId ($platform)");

    // Retrieve FCM token (Mock / Real token handling)
    // Note: When firebase_messaging Flutter package is included in pubspec.yaml:
    // FirebaseMessaging messaging = FirebaseMessaging.instance;
    // NotificationSettings settings = await messaging.requestPermission(alert: true, badge: true, sound: true);
    // String? token = await messaging.getToken();

    if (currentFcmToken != null) {
      await registerToken(
        deviceId: deviceId,
        platform: platform,
        fcmToken: currentFcmToken!,
        deviceName: deviceName,
        appVersion: appVersion,
      );
    }
  }

  /// Register device token with VKShop backend
  static Future<bool> registerToken({
    required String deviceId,
    required String platform,
    required String fcmToken,
    String? deviceName,
    String? appVersion,
  }) async {
    currentDeviceId = deviceId;
    currentFcmToken = fcmToken;
    
    return await ApiService.registerAdminDevice(
      deviceId: deviceId,
      platform: platform,
      fcmToken: fcmToken,
      deviceName: deviceName,
      appVersion: appVersion,
    );
  }

  /// Handle Notification Tap Event Routing
  static void handleNotificationTap(Map<String, dynamic> data, {Function(String route, Map<String, dynamic> params)? navigateTo}) {
    final String type = data["type"]?.toString() ?? "";
    final String orderId = data["order_id"]?.toString() ?? "";
    final String whatsappMessageId = data["whatsapp_message_id"]?.toString() ?? "";

    debugPrint("FCM Notification Tapped: type=$type, orderId=$orderId, whatsappMessageId=$whatsappMessageId");

    if (type == "new_order" && orderId.isNotEmpty) {
      // Tap on new_order notification -> navigate to Admin Order detail screen
      if (navigateTo != null) {
        navigateTo("/admin/orders/detail", {"order_id": orderId});
      }
    } else if ((type == "whatsapp_created" || type == "whatsapp_message") && whatsappMessageId.isNotEmpty) {
      // Tap on whatsapp notification -> navigate to Admin WhatsApp Queue screen
      if (navigateTo != null) {
        navigateTo("/admin/whatsapp", {"message_id": whatsappMessageId});
      }
    }
  }

  /// Send Periodic Heartbeat to Backend
  static Future<void> sendHeartbeat() async {
    if (currentDeviceId != null) {
      await ApiService.sendDeviceHeartbeat(currentDeviceId!);
    }
  }

  /// Unregister device on admin logout
  static Future<void> unregisterOnLogout() async {
    if (currentDeviceId != null) {
      await ApiService.unregisterAdminDevice(currentDeviceId!);
    }
  }
}
