# AWS RDS Utils

## [rds_snapshot.py](rds_snapshot.py)
- ec2나 로컬에서 스냅샷으로 백업을 할 수 있는 코드
  - 로컬에서는 SSO를 통한 로그인 후 Profile을 이용하여 동작
  - ec2에서는 IAM Role를 이용한 동작
- RDS, Aurora Cluster 두가지 타입의 스냅샷 가능
- 백업 후 설정한 기간(월)보다 오래된 스냅샷 삭제 가능

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