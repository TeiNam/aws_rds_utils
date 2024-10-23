# AWS RDS Utils

## rds_snapshot.py
- ec2나 로컬에서 스냅샷으로 백업을 할 수 있는 코드

### EC2 설정시 IAM Role

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "rds:CreateDBSnapshot",
                "rds:DeleteDBSnapshot",
                "rds:DescribeDBSnapshots"
            ],
            "Resource": "*"
        }
    ]
}
```