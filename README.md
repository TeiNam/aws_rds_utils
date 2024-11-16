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

### snapshot_config.yml
- 백업 인스턴스 설정 파일

#### 전체 옵션

```yaml
# AWS 기본 설정
aws:
  default_profile: 'AdministratorAccess'               # 기본 AWS SSO 프로필
  default_region: 'ap-northeast-2'                     # 기본 AWS 리전

# 스냅샷 기본 설정
snapshot:
  default_retention_months: 3        # 기본 스냅샷 보관 기간 (월)
  
# 로깅 설정 (선택사항)
logging:
  level: 'INFO'                      # 로깅 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  file: 'snapshot.log'               # 로그 파일 경로
  format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # 로그 형식

# DB 인스턴스 설정
instances:
  # Aurora 예제 1: 기본 설정 사용
  - identifier: 'dev-aurora-1'       # 인스턴스 식별자 (필수)
    type: 'aurora'                   # 인스턴스 유형 (필수, 'aurora' 또는 'rds')
    # 기본값들을 사용하므로 aws_profile, aws_region, retention_months는 생략

  # Aurora 예제 2: 모든 설정 명시
  - identifier: 'prod-aurora-2'
    type: 'aurora'
    aws_profile: 'AdministratorAccess-2'  # 다른 AWS 프로필
    aws_region: 'ap-northeast-1'     # 다른 리전
    retention_months: 12             # 12개월 보관
    description: '프로덕션 Aurora 클러스터'  # 설명 (선택사항)

  # RDS 예제 1: 일부 설정만 변경
  - identifier: 'dev-rds-1'
    type: 'rds'
    retention_months: 1              # 1개월만 보관
    # 나머지는 기본값 사용

  # RDS 예제 2: 다른 계정의 다른 리전
  - identifier: 'prod-rds-2'
    type: 'rds'
    aws_profile: 'AdminRole-999999999999'
    aws_region: 'ap-southeast-1'
    retention_months: 6

  # 개발 환경 예제
  - identifier: 'dev-channel-admin-api'
    type: 'aurora'
    aws_profile: 'AdministratorAccess'
    aws_region: 'ap-northeast-2'
    retention_months: 1
    description: '개발 환경 채널 관리 API DB'

  # 스테이징 환경 예제
  - identifier: 'staging-user-db'
    type: 'rds'
    aws_profile: 'AdminRole-111111111111'
    aws_region: 'ap-northeast-2'
    retention_months: 2
    description: '스테이징 환경 사용자 DB'

  # 프로덕션 환경 예제
  - identifier: 'prod-payment-db'
    type: 'aurora'
    aws_profile: 'AdminRole-222222222222'
    aws_region: 'ap-northeast-2'
    retention_months: 12
    description: '프로덕션 결제 DB'
```

#### 실제 사용 예시

```yaml
# 간단한 설정 예시
aws:
  default_profile: 'AdminRole-111111111111'
  default_region: 'ap-northeast-2'

snapshot:
  default_retention_months: 3

instances:
  - identifier: 'dev-db'
    type: 'aurora'
    retention_months: 1

  - identifier: 'prod-db'
    type: 'aurora'
    aws_profile: 'AdminRole-222222222222'
    retention_months: 12
```

#### 멀티 계정/리전 설정 예시

```yaml
aws:
  default_profile: 'AdminRole-111111111111'
  default_region: 'ap-northeast-2'

snapshot:
  default_retention_months: 3

instances:
  # 개발 계정 인스턴스
  - identifier: 'dev-db'
    type: 'aurora'
    aws_profile: 'AdminRole-111111111111'
    retention_months: 1

  # 프로덕션 계정 인스턴스 (다른 리전)
  - identifier: 'prod-db-tokyo'
    type: 'aurora'
    aws_profile: 'AdminRole-222222222222'
    aws_region: 'ap-northeast-1'
    retention_months: 12

  # 백업 계정 인스턴스
  - identifier: 'backup-db'
    type: 'rds'
    aws_profile: 'AdminRole-333333333333'
    retention_months: 24
```


## [scheduler.py](scheduler.py)
- 유틸을 주기적으로 사용하기 위한 스케줄러

### 설정 파일 전체 옵션 [scheduler_config.yml](scheduler_config.yml)

```yaml
# 전체 작업 설정
tasks:
  # 작업 1: 일일 백업 예시
  daily_backup_task:
    # 필수 설정
    module: "rds_snapshot"            # 실행할 파이썬 모듈 이름
    function: "process_instance"      # 실행할 함수 이름
    
    # 스케줄 설정 (필수)
    schedule:
      # type 옵션:
      # - interval: 분 단위 간격으로 실행
      # - daily: 매일 특정 시간에 실행
      # - weekly: 매주 특정 요일, 시간에 실행
      # - monthly: 매월 특정 날짜, 시간에 실행
      type: "daily"
      at: "02:00"                    # 실행 시간 (24시간 형식)
    
    # 선택적 설정
    enabled: true                     # 작업 활성화 여부 (기본값: true)
    description: "일일 백업 작업"      # 작업 설명
    args: []                         # 함수 위치 인자 (리스트)
    kwargs: {}                       # 함수 키워드 인자 (딕셔너리)

  # 작업 2: 주간 백업 예시
  weekly_backup_task:
    module: "rds_snapshot"
    function: "process_instance"
    schedule:
      type: "weekly"
      at: "Monday 03:00"             # 요일 시간 형식 (요일 첫 글자 대문자)
    enabled: true
    description: "주간 백업 작업"

  # 작업 3: 월간 백업 예시
  monthly_backup_task:
    module: "rds_snapshot"
    function: "process_instance"
    schedule:
      type: "monthly"
      at: "1 04:00"                  # 일자 시간 형식 (1-28)
    enabled: true
    description: "월간 백업 작업"

  # 작업 4: 간격 실행 예시
  interval_task:
    module: "custom_module"
    function: "custom_function"
    schedule:
      type: "interval"
      minutes: 30                    # 실행 간격 (분)
    enabled: true
    description: "30분마다 실행"
    # 함수 인자 예시
    args: ["arg1", "arg2"]
    kwargs: 
      param1: "value1"
      param2: "value2"

# 로깅 설정
logging:
  level: "INFO"                      # 로깅 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  file: "scheduler.log"              # 로그 파일 경로
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"  # 로그 형식
```
#### example

```yaml
tasks:
  # RDS 일일 백업
  rds_daily_backup:
    module: "rds_snapshot"
    function: "process_instance"
    schedule:
      type: "daily"
      at: "02:00"
    enabled: true
    description: "RDS 일일 백업"
    kwargs:
      instance_type: "production"

  # 매 30분마다 모니터링
  monitoring_task:
    module: "monitoring"
    function: "check_status"
    schedule:
      type: "interval"
      minutes: 30
    enabled: true
    args: ["production"]
    kwargs:
      alert_threshold: 90
      notify_email: "admin@example.com"

logging:
  level: "INFO"
  file: "scheduler.log"
```
