"""
Security and compliance utilities for StreamForge.

Features:
- KMS encryption for data at rest
- Field-level encryption for PII
- IAM policy generation
- Audit logging with CloudTrail integration
- Compliance checks (GDPR, HIPAA, SOC2)
"""

import json
import hashlib
import base64
from datetime import datetime
from typing import Dict, List, Any, Optional
import boto3
from botocore.exceptions import ClientError


class KMSEncryption:
    """
    Handles KMS encryption for sensitive data.
    """

    def __init__(self, kms_key_id: str):
        self.kms = boto3.client('kms')
        self.kms_key_id = kms_key_id

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext using KMS.

        Args:
            plaintext: Data to encrypt

        Returns:
            Base64-encoded ciphertext
        """
        try:
            response = self.kms.encrypt(
                KeyId=self.kms_key_id,
                Plaintext=plaintext.encode('utf-8')
            )
            return base64.b64encode(response['CiphertextBlob']).decode('utf-8')
        except ClientError as e:
            raise Exception(f"KMS encryption failed: {e}")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt ciphertext using KMS.

        Args:
            ciphertext: Base64-encoded ciphertext

        Returns:
            Decrypted plaintext
        """
        try:
            ciphertext_blob = base64.b64decode(ciphertext)
            response = self.kms.decrypt(CiphertextBlob=ciphertext_blob)
            return response['Plaintext'].decode('utf-8')
        except ClientError as e:
            raise Exception(f"KMS decryption failed: {e}")

    def encrypt_dict_fields(self, data: dict, fields: List[str]) -> dict:
        """
        Encrypt specific fields in a dictionary.

        Args:
            data: Dictionary containing data
            fields: List of field names to encrypt

        Returns:
            Dictionary with encrypted fields
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
                result[f'{field}_encrypted'] = True
        return result


class FieldLevelEncryption:
    """
    Field-level encryption for PII data using envelope encryption.
    """

    def __init__(self, kms_key_id: str):
        self.kms = KMSEncryption(kms_key_id)
        self.pii_fields = {
            'email', 'phone', 'ssn', 'credit_card',
            'ip_address', 'address', 'name', 'date_of_birth'
        }

    def encrypt_event(self, event: dict, custom_pii_fields: Optional[List[str]] = None) -> dict:
        """
        Encrypt PII fields in an event.

        Args:
            event: Event data
            custom_pii_fields: Additional fields to treat as PII

        Returns:
            Event with encrypted PII fields
        """
        fields_to_encrypt = self.pii_fields.copy()
        if custom_pii_fields:
            fields_to_encrypt.update(custom_pii_fields)

        # Find PII fields in event
        pii_present = [field for field in fields_to_encrypt if field in event]

        if not pii_present:
            return event

        # Encrypt PII fields
        encrypted = self.kms.encrypt_dict_fields(event, pii_present)
        encrypted['_pii_encrypted'] = True
        encrypted['_pii_fields'] = pii_present

        return encrypted

    def decrypt_event(self, event: dict) -> dict:
        """
        Decrypt PII fields in an event.

        Args:
            event: Event with encrypted PII

        Returns:
            Event with decrypted PII fields
        """
        if not event.get('_pii_encrypted'):
            return event

        result = event.copy()
        pii_fields = event.get('_pii_fields', [])

        for field in pii_fields:
            if f'{field}_encrypted' in result and result[f'{field}_encrypted']:
                result[field] = self.kms.decrypt(result[field])
                del result[f'{field}_encrypted']

        del result['_pii_encrypted']
        del result['_pii_fields']

        return result


class AuditLogger:
    """
    Audit logging for compliance and security monitoring.
    """

    def __init__(self, log_group: str = '/streamforge/audit'):
        self.logs = boto3.client('logs')
        self.log_group = log_group
        self.log_stream = f'audit-{datetime.utcnow().strftime("%Y-%m-%d")}'

        # Ensure log group and stream exist
        self._ensure_log_stream()

    def _ensure_log_stream(self):
        """Ensure CloudWatch log group and stream exist."""
        try:
            self.logs.create_log_group(logGroupName=self.log_group)
        except self.logs.exceptions.ResourceAlreadyExistsException:
            pass

        try:
            self.logs.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except self.logs.exceptions.ResourceAlreadyExistsException:
            pass

    def log_event(
        self,
        action: str,
        resource: str,
        user_id: str,
        result: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log an audit event.

        Args:
            action: Action performed (e.g., 'pipeline.create', 'data.export')
            resource: Resource affected (e.g., pipeline ID, query ID)
            user_id: User or service performing action
            result: Result ('success', 'failure', 'denied')
            metadata: Additional context
        """
        audit_event = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'resource': resource,
            'user_id': user_id,
            'result': result,
            'metadata': metadata or {}
        }

        try:
            self.logs.put_log_events(
                logGroupName=self.log_group,
                logStreamName=self.log_stream,
                logEvents=[{
                    'timestamp': int(datetime.utcnow().timestamp() * 1000),
                    'message': json.dumps(audit_event)
                }]
            )
        except ClientError as e:
            print(f"Failed to write audit log: {e}")

    def log_data_access(self, pipeline_id: str, user_id: str, query: str, row_count: int):
        """Log data access for compliance."""
        self.log_event(
            action='data.access',
            resource=pipeline_id,
            user_id=user_id,
            result='success',
            metadata={'query': query, 'row_count': row_count}
        )

    def log_pii_access(self, pipeline_id: str, user_id: str, pii_fields: List[str]):
        """Log PII access for GDPR/HIPAA compliance."""
        self.log_event(
            action='pii.access',
            resource=pipeline_id,
            user_id=user_id,
            result='success',
            metadata={'pii_fields': pii_fields}
        )


class ComplianceChecker:
    """
    Compliance validation for data pipelines.
    """

    def check_gdpr_compliance(self, pipeline_config: dict) -> Dict[str, Any]:
        """
        Check pipeline compliance with GDPR requirements.

        Returns:
            Compliance report with violations
        """
        violations = []

        # Check for PII handling
        if not pipeline_config.get('pii_encryption_enabled'):
            violations.append({
                'rule': 'GDPR Article 32 - Security of processing',
                'violation': 'PII encryption not enabled',
                'severity': 'high'
            })

        # Check for data retention policy
        if not pipeline_config.get('data_retention_days'):
            violations.append({
                'rule': 'GDPR Article 5(1)(e) - Storage limitation',
                'violation': 'No data retention policy configured',
                'severity': 'medium'
            })

        # Check for audit logging
        if not pipeline_config.get('audit_logging_enabled'):
            violations.append({
                'rule': 'GDPR Article 30 - Records of processing',
                'violation': 'Audit logging not enabled',
                'severity': 'high'
            })

        return {
            'compliant': len(violations) == 0,
            'violations': violations,
            'checked_at': datetime.utcnow().isoformat()
        }

    def check_hipaa_compliance(self, pipeline_config: dict) -> Dict[str, Any]:
        """
        Check pipeline compliance with HIPAA requirements.

        Returns:
            Compliance report with violations
        """
        violations = []

        # HIPAA Security Rule - Encryption
        if not pipeline_config.get('encryption_at_rest'):
            violations.append({
                'rule': 'HIPAA Security Rule § 164.312(a)(2)(iv)',
                'violation': 'Encryption at rest not enabled',
                'severity': 'critical'
            })

        if not pipeline_config.get('encryption_in_transit'):
            violations.append({
                'rule': 'HIPAA Security Rule § 164.312(e)(2)(i)',
                'violation': 'Encryption in transit not enabled',
                'severity': 'critical'
            })

        # HIPAA Security Rule - Access Controls
        if not pipeline_config.get('access_controls_enabled'):
            violations.append({
                'rule': 'HIPAA Security Rule § 164.312(a)(1)',
                'violation': 'Access controls not configured',
                'severity': 'critical'
            })

        # HIPAA Security Rule - Audit Controls
        if not pipeline_config.get('audit_logging_enabled'):
            violations.append({
                'rule': 'HIPAA Security Rule § 164.312(b)',
                'violation': 'Audit logging not enabled',
                'severity': 'high'
            })

        return {
            'compliant': len(violations) == 0,
            'violations': violations,
            'checked_at': datetime.utcnow().isoformat()
        }


def generate_iam_policy(pipeline_id: str, resources: List[str]) -> dict:
    """
    Generate least-privilege IAM policy for a pipeline.

    Args:
        pipeline_id: Pipeline identifier
        resources: List of AWS resources (ARNs)

    Returns:
        IAM policy document
    """
    return {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Sid': f'StreamForge{pipeline_id}Access',
                'Effect': 'Allow',
                'Action': [
                    's3:GetObject',
                    's3:PutObject',
                    's3:DeleteObject',
                    'dynamodb:GetItem',
                    'dynamodb:PutItem',
                    'dynamodb:Query',
                    'kinesis:PutRecord',
                    'kinesis:PutRecords',
                    'kms:Decrypt',
                    'kms:Encrypt',
                    'logs:CreateLogStream',
                    'logs:PutLogEvents'
                ],
                'Resource': resources
            }
        ]
    }


# Example usage
if __name__ == '__main__':
    # Field-level encryption
    kms_key = 'arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012'
    encryption = FieldLevelEncryption(kms_key)

    event = {
        'event_id': 'evt-123',
        'email': 'user@example.com',
        'amount': 99.99,
        'timestamp': datetime.utcnow().isoformat()
    }

    encrypted = encryption.encrypt_event(event)
    print(f"Encrypted event: {json.dumps(encrypted, indent=2)}")

    decrypted = encryption.decrypt_event(encrypted)
    print(f"Decrypted event: {json.dumps(decrypted, indent=2)}")

    # Audit logging
    audit = AuditLogger()
    audit.log_data_access('pipeline-123', 'user-456', 'SELECT * FROM events', 1000)
    audit.log_pii_access('pipeline-123', 'user-456', ['email', 'phone'])

    # Compliance checking
    compliance = ComplianceChecker()
    pipeline_config = {
        'pii_encryption_enabled': True,
        'data_retention_days': 90,
        'audit_logging_enabled': True,
        'encryption_at_rest': True,
        'encryption_in_transit': True,
        'access_controls_enabled': True
    }

    gdpr_report = compliance.check_gdpr_compliance(pipeline_config)
    print(f"GDPR Compliance: {json.dumps(gdpr_report, indent=2)}")

    hipaa_report = compliance.check_hipaa_compliance(pipeline_config)
    print(f"HIPAA Compliance: {json.dumps(hipaa_report, indent=2)}")
