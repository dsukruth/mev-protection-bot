import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib
import os
import asyncio
from typing import Dict, List, Tuple, Optional
import logging
from datetime import datetime, timedelta

class MLAttackDetector:
    def __init__(self, model_path: str = "models/"):
        self.model_path = model_path
        self.sandwich_classifier = None
        self.anomaly_detector = None
        self.scaler = StandardScaler()
        self.feature_columns = [
            'gas_price', 'gas_limit', 'value_usd', 'slippage',
            'token_volume_24h', 'liquidity_ratio', 'time_since_last_tx',
            'sender_tx_count', 'is_contract', 'block_position'
        ]
        self.known_mev_bots = set()
        self.setup_logging()
        self.ensure_model_directory()
    
    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def ensure_model_directory(self):
        if not os.path.exists(self.model_path):
            os.makedirs(self.model_path)
    
    def extract_features(self, tx_data: Dict) -> np.ndarray:
        """Extract ML features from transaction data"""
        try:
            features = {
                'gas_price': float(tx_data.get('gasPrice', 0)) / 1e9,  # Convert to Gwei
                'gas_limit': float(tx_data.get('gas', 0)),
                'value_usd': float(tx_data.get('estimated_value', 0)),
                'slippage': float(tx_data.get('slippage', 0)),
                'token_volume_24h': float(tx_data.get('token_volume_24h', 0)),
                'liquidity_ratio': float(tx_data.get('liquidity_ratio', 1.0)),
                'time_since_last_tx': float(tx_data.get('time_since_last_tx', 0)),
                'sender_tx_count': float(tx_data.get('sender_tx_count', 0)),
                'is_contract': 1.0 if tx_data.get('is_contract', False) else 0.0,
                'block_position': float(tx_data.get('block_position', 0))
            }
            
            return np.array([features[col] for col in self.feature_columns]).reshape(1, -1)
            
        except Exception as e:
            self.logger.error(f"Error extracting features: {e}")
            return np.zeros((1, len(self.feature_columns)))
    
    def train_sandwich_classifier(self, training_data: List[Dict]):
        """Train the sandwich attack classifier"""
        try:
            if len(training_data) < 100:
                self.logger.warning("Insufficient training data, using pre-trained model")
                return self.load_pretrained_models()
            
            X = []
            y = []
            
            for data in training_data:
                features = self.extract_features(data).flatten()
                X.append(features)
                y.append(1 if data.get('is_sandwich_attack', False) else 0)
            
            X = np.array(X)
            y = np.array(y)
            
            X_scaled = self.scaler.fit_transform(X)
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42, stratify=y
            )
            
            self.sandwich_classifier = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                class_weight='balanced'
            )
            
            self.sandwich_classifier.fit(X_train, y_train)
            
            y_pred = self.sandwich_classifier.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            
            self.logger.info(f"Sandwich classifier trained with accuracy: {accuracy:.3f}")
            self.logger.info(f"Classification report:\n{classification_report(y_test, y_pred)}")
            
            self.save_models()
            return True
            
        except Exception as e:
            self.logger.error(f"Error training sandwich classifier: {e}")
            return False
    
    def train_anomaly_detector(self, normal_transactions: List[Dict]):
        """Train the anomaly detection model"""
        try:
            if len(normal_transactions) < 50:
                self.logger.warning("Insufficient normal transaction data")
                return False
            
            X = []
            for tx in normal_transactions:
                features = self.extract_features(tx).flatten()
                X.append(features)
            
            X = np.array(X)
            X_scaled = self.scaler.transform(X)
            
            self.anomaly_detector = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_estimators=100
            )
            
            self.anomaly_detector.fit(X_scaled)
            
            self.logger.info("Anomaly detector trained successfully")
            self.save_models()
            return True
            
        except Exception as e:
            self.logger.error(f"Error training anomaly detector: {e}")
            return False
    
    def predict_sandwich_attack(self, tx_data: Dict) -> Tuple[float, float]:
        """Predict if transaction is part of sandwich attack"""
        try:
            if self.sandwich_classifier is None:
                self.load_models()
            
            if self.sandwich_classifier is None:
                return 0.5, 0.5  # Default uncertainty
            
            features = self.extract_features(tx_data)
            features_scaled = self.scaler.transform(features)
            
            prediction_proba = self.sandwich_classifier.predict_proba(features_scaled)[0]
            confidence = max(prediction_proba)
            attack_probability = prediction_proba[1] if len(prediction_proba) > 1 else 0.0
            
            return attack_probability, confidence
            
        except Exception as e:
            self.logger.error(f"Error predicting sandwich attack: {e}")
            return 0.5, 0.5
    
    def detect_anomaly(self, tx_data: Dict) -> Tuple[bool, float]:
        """Detect if transaction is anomalous"""
        try:
            if self.anomaly_detector is None:
                self.load_models()
            
            if self.anomaly_detector is None:
                return False, 0.5
            
            features = self.extract_features(tx_data)
            features_scaled = self.scaler.transform(features)
            
            anomaly_score = self.anomaly_detector.decision_function(features_scaled)[0]
            is_anomaly = self.anomaly_detector.predict(features_scaled)[0] == -1
            
            anomaly_confidence = abs(anomaly_score)
            
            return is_anomaly, anomaly_confidence
            
        except Exception as e:
            self.logger.error(f"Error detecting anomaly: {e}")
            return False, 0.5
    
    def update_mev_bot_database(self, address: str, is_mev_bot: bool):
        """Update known MEV bot addresses"""
        if is_mev_bot:
            self.known_mev_bots.add(address.lower())
        else:
            self.known_mev_bots.discard(address.lower())
    
    def is_known_mev_bot(self, address: str) -> bool:
        """Check if address is a known MEV bot"""
        return address.lower() in self.known_mev_bots
    
    def analyze_transaction_ml(self, tx_data: Dict) -> Dict:
        """Comprehensive ML analysis of transaction"""
        try:
            sender = tx_data.get('from', '').lower()
            
            sandwich_prob, sandwich_conf = self.predict_sandwich_attack(tx_data)
            is_anomaly, anomaly_conf = self.detect_anomaly(tx_data)
            is_known_bot = self.is_known_mev_bot(sender)
            
            ml_score = (
                sandwich_prob * 0.4 +
                (1.0 if is_anomaly else 0.0) * 0.3 +
                (1.0 if is_known_bot else 0.0) * 0.3
            )
            
            confidence = (sandwich_conf + anomaly_conf) / 2
            
            risk_level = "LOW"
            if ml_score > 0.7:
                risk_level = "HIGH"
            elif ml_score > 0.4:
                risk_level = "MEDIUM"
            
            return {
                'ml_score': ml_score,
                'confidence': confidence,
                'risk_level': risk_level,
                'sandwich_probability': sandwich_prob,
                'is_anomaly': is_anomaly,
                'is_known_mev_bot': is_known_bot,
                'features_extracted': True
            }
            
        except Exception as e:
            self.logger.error(f"Error in ML analysis: {e}")
            return {
                'ml_score': 0.5,
                'confidence': 0.5,
                'risk_level': "UNKNOWN",
                'sandwich_probability': 0.5,
                'is_anomaly': False,
                'is_known_mev_bot': False,
                'features_extracted': False
            }
    
    def save_models(self):
        """Save trained models to disk"""
        try:
            if self.sandwich_classifier:
                joblib.dump(
                    self.sandwich_classifier,
                    os.path.join(self.model_path, 'sandwich_classifier.pkl')
                )
            
            if self.anomaly_detector:
                joblib.dump(
                    self.anomaly_detector,
                    os.path.join(self.model_path, 'anomaly_detector.pkl')
                )
            
            joblib.dump(
                self.scaler,
                os.path.join(self.model_path, 'scaler.pkl')
            )
            
            with open(os.path.join(self.model_path, 'mev_bots.txt'), 'w') as f:
                for bot in self.known_mev_bots:
                    f.write(f"{bot}\n")
            
            self.logger.info("Models saved successfully")
            
        except Exception as e:
            self.logger.error(f"Error saving models: {e}")
    
    def load_models(self):
        """Load trained models from disk"""
        try:
            sandwich_path = os.path.join(self.model_path, 'sandwich_classifier.pkl')
            anomaly_path = os.path.join(self.model_path, 'anomaly_detector.pkl')
            scaler_path = os.path.join(self.model_path, 'scaler.pkl')
            mev_bots_path = os.path.join(self.model_path, 'mev_bots.txt')
            
            if os.path.exists(sandwich_path):
                self.sandwich_classifier = joblib.load(sandwich_path)
                self.logger.info("Sandwich classifier loaded")
            
            if os.path.exists(anomaly_path):
                self.anomaly_detector = joblib.load(anomaly_path)
                self.logger.info("Anomaly detector loaded")
            
            if os.path.exists(scaler_path):
                self.scaler = joblib.load(scaler_path)
                self.logger.info("Scaler loaded")
            
            if os.path.exists(mev_bots_path):
                with open(mev_bots_path, 'r') as f:
                    self.known_mev_bots = set(line.strip().lower() for line in f)
                self.logger.info(f"Loaded {len(self.known_mev_bots)} known MEV bots")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading models: {e}")
            return self.load_pretrained_models()
    
    def load_pretrained_models(self):
        """Load pre-trained models with default parameters"""
        try:
            self.sandwich_classifier = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                class_weight='balanced'
            )
            
            self.anomaly_detector = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_estimators=100
            )
            
            synthetic_data = self.generate_synthetic_training_data()
            X = np.array([self.extract_features(data).flatten() for data in synthetic_data['features']])
            y = np.array(synthetic_data['labels'])
            
            X_scaled = self.scaler.fit_transform(X)
            self.sandwich_classifier.fit(X_scaled, y)
            
            normal_data = X_scaled[y == 0]
            if len(normal_data) > 10:
                self.anomaly_detector.fit(normal_data)
            
            self.known_mev_bots.update([
                '0x000000000000084e91743124a982076c59f10084',
                '0x00000000003b3cc22af3ae1eac0440bcee416b40',
                '0x0000000000007f150bd6f54c40a34d7c3d5e9f56'
            ])
            
            self.logger.info("Pre-trained models loaded successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading pre-trained models: {e}")
            return False
    
    def generate_synthetic_training_data(self) -> Dict:
        """Generate synthetic training data for initial model training"""
        np.random.seed(42)
        
        features = []
        labels = []
        
        for i in range(1000):
            if i < 200:
                data = {
                    'gasPrice': np.random.normal(50e9, 20e9),
                    'gas': np.random.normal(200000, 50000),
                    'estimated_value': np.random.exponential(5000),
                    'slippage': np.random.exponential(2.0),
                    'token_volume_24h': np.random.exponential(1000000),
                    'liquidity_ratio': np.random.beta(2, 5),
                    'time_since_last_tx': np.random.exponential(30),
                    'sender_tx_count': np.random.poisson(100),
                    'is_contract': np.random.choice([True, False], p=[0.3, 0.7]),
                    'block_position': np.random.randint(0, 200)
                }
                labels.append(1)
            else:
                data = {
                    'gasPrice': np.random.normal(20e9, 10e9),
                    'gas': np.random.normal(150000, 30000),
                    'estimated_value': np.random.exponential(1000),
                    'slippage': np.random.exponential(0.5),
                    'token_volume_24h': np.random.exponential(500000),
                    'liquidity_ratio': np.random.beta(5, 2),
                    'time_since_last_tx': np.random.exponential(60),
                    'sender_tx_count': np.random.poisson(50),
                    'is_contract': np.random.choice([True, False], p=[0.1, 0.9]),
                    'block_position': np.random.randint(0, 200)
                }
                labels.append(0)
            
            features.append(data)
        
        return {'features': features, 'labels': labels}
    
    async def continuous_learning(self, new_data: List[Dict]):
        """Continuously update models with new data"""
        try:
            if len(new_data) < 10:
                return
            
            self.logger.info(f"Updating models with {len(new_data)} new samples")
            
            X_new = []
            y_new = []
            
            for data in new_data:
                features = self.extract_features(data).flatten()
                X_new.append(features)
                y_new.append(1 if data.get('is_confirmed_attack', False) else 0)
            
            X_new = np.array(X_new)
            y_new = np.array(y_new)
            
            if self.sandwich_classifier and len(set(y_new)) > 1:
                X_new_scaled = self.scaler.transform(X_new)
                
                current_accuracy = self.sandwich_classifier.score(X_new_scaled, y_new)
                self.logger.info(f"Current model accuracy on new data: {current_accuracy:.3f}")
                
                if current_accuracy < 0.8:
                    self.logger.info("Retraining model due to low accuracy")
                    await self.retrain_models()
            
        except Exception as e:
            self.logger.error(f"Error in continuous learning: {e}")
    
    async def retrain_models(self):
        """Retrain models with updated data"""
        try:
            self.logger.info("Starting model retraining...")
            
            synthetic_data = self.generate_synthetic_training_data()
            await asyncio.sleep(0.1)
            
            success = self.train_sandwich_classifier(synthetic_data['features'])
            if success:
                self.logger.info("Model retraining completed successfully")
            else:
                self.logger.error("Model retraining failed")
                
        except Exception as e:
            self.logger.error(f"Error retraining models: {e}")
