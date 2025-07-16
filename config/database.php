<?php
// FILE LOCATION: /config/database.php
// Database configuration for Render deployment

// Enable error reporting for development
error_reporting(E_ALL);
ini_set('display_errors', 1);

// Database configuration - Render will provide these as environment variables
$db_host = $_ENV['DATABASE_HOST'] ?? 'localhost';
$db_name = $_ENV['DATABASE_NAME'] ?? 'stories_db';
$db_user = $_ENV['DATABASE_USER'] ?? 'root';
$db_pass = $_ENV['DATABASE_PASSWORD'] ?? '';
$db_port = $_ENV['DATABASE_PORT'] ?? '5432';

// For local development, you can set these directly:
// $db_host = 'localhost';
// $db_name = 'stories_db';
// $db_user = 'root';
// $db_pass = 'your_password';
// $db_port = '3306'; // MySQL port

try {
    // Create PDO connection (PostgreSQL for Render)
    $dsn = "pgsql:host={$db_host};port={$db_port};dbname={$db_name}";
    $pdo = new PDO($dsn, $db_user, $db_pass, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    
    // Set charset for proper handling of special characters
    $pdo->exec("SET NAMES utf8mb4");
    
} catch (PDOException $e) {
    // Log error and show user-friendly message
    error_log("Database connection failed: " . $e->getMessage());
    
    // In production, don't show detailed error messages
    if (isset($_ENV['RENDER_SERVICE_NAME'])) {
        die(json_encode([
            'success' => false,
            'message' => 'Database connection failed. Please try again later.'
        ]));
    } else {
        die("Database connection failed: " . $e->getMessage());
    }
}

// Helper function to check if user has active subscription
function hasActiveSubscription($user_id) {
    global $pdo;
    
    $stmt = $pdo->prepare("
        SELECT COUNT(*) as count 
        FROM subscriptions 
        WHERE user_id = ? 
        AND status = 'active' 
        AND current_period_end > NOW()
    ");
    $stmt->execute([$user_id]);
    $result = $stmt->fetch();
    
    return $result['count'] > 0;
}

// Helper function to get user by ID
function getUserById($user_id) {
    global $pdo;
    
    $stmt = $pdo->prepare("SELECT id, email, is_admin, created_at FROM users WHERE id = ?");
    $stmt->execute([$user_id]);
    
    return $stmt->fetch();
}

// Helper function to get user by email
function getUserByEmail($email) {
    global $pdo;
    
    $stmt = $pdo->prepare("SELECT id, email, password_hash, is_admin FROM users WHERE email = ?");
    $stmt->execute([$email]);
    
    return $stmt->fetch();
}

// Helper function to create new user
function createUser($email, $password) {
    global $pdo;
    
    $password_hash = password_hash($password, PASSWORD_DEFAULT);
    
    $stmt = $pdo->prepare("INSERT INTO users (email, password_hash) VALUES (?, ?)");
    $stmt->execute([$email, $password_hash]);
    
    return $pdo->lastInsertId();
}

// Helper function to create or update subscription
function updateSubscription($user_id, $stripe_customer_id, $stripe_subscription_id, $status, $current_period_end) {
    global $pdo;
    
    $stmt = $pdo->prepare("
        INSERT INTO subscriptions (user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end) 
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (user_id) 
        DO UPDATE SET 
            stripe_customer_id = EXCLUDED.stripe_customer_id,
            stripe_subscription_id = EXCLUDED.stripe_subscription_id,
            status = EXCLUDED.status,
            current_period_end = EXCLUDED.current_period_end,
            updated_at = CURRENT_TIMESTAMP
    ");
    
    return $stmt->execute([$user_id, $stripe_customer_id, $stripe_subscription_id, $status, $current_period_end]);
}

// Helper function to get all active videos
function getActiveVideos() {
    global $pdo;
    
    $stmt = $pdo->prepare("
        SELECT id, title, description, youtube_url, youtube_video_id, thumbnail_url, created_at
        FROM videos 
        WHERE is_active = true 
        ORDER BY created_at DESC
    ");
    $stmt->execute();
    
    return $stmt->fetchAll();
}

// Helper function to add new video
function addVideo($title, $description, $youtube_url, $youtube_video_id, $thumbnail_url = null) {
    global $pdo;
    
    $stmt = $pdo->prepare("
        INSERT INTO videos (title, description, youtube_url, youtube_video_id, thumbnail_url) 
        VALUES (?, ?, ?, ?, ?)
    ");
    
    return $stmt->execute([$title, $description, $youtube_url, $youtube_video_id, $thumbnail_url]);
}

// Helper function to extract YouTube video ID from URL
function extractYouTubeVideoId($url) {
    $pattern = '/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/i';
    preg_match($pattern, $url, $matches);
    return isset($matches[1]) ? $matches[1] : false;
}

// Helper function to get YouTube thumbnail URL
function getYouTubeThumbnail($video_id) {
    return "https://img.youtube.com/vi/{$video_id}/maxresdefault.jpg";
}

// Session management functions
function startSession() {
    if (session_status() === PHP_SESSION_NONE) {
        session_start();
    }
}

function isLoggedIn() {
    startSession();
    return isset($_SESSION['user_id']);
}

function requireLogin() {
    if (!isLoggedIn()) {
        http_response_code(401);
        echo json_encode([
            'success' => false,
            'message' => 'Authentication required'
        ]);
        exit();
    }
}

function requireSubscription() {
    requireLogin();
    
    if (!hasActiveSubscription($_SESSION['user_id'])) {
        http_response_code(402);
        echo json_encode([
            'success' => false,
            'message' => 'Active subscription required'
        ]);
        exit();
    }
}

function requireAdmin() {
    requireLogin();
    
    $user = getUserById($_SESSION['user_id']);
    if (!$user || !$user['is_admin']) {
        http_response_code(403);
        echo json_encode([
            'success' => false,
            'message' => 'Admin access required'
        ]);
        exit();
    }
}

// Set JSON response headers
function setJSONHeaders() {
    header('Content-Type: application/json');
    header('Access-Control-Allow-Origin: *');
    header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type, Authorization');
}

// Handle preflight requests
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    setJSONHeaders();
    exit();
}

?>
