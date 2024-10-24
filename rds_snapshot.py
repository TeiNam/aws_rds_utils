import boto3
import datetime
import random
import string
import re
import os
import time
import yaml
from datetime import datetime, timedelta
from botocore.exceptions import ProfileNotFound, NoCredentialsError


def load_config(config_path='snapshot_config.yml'):
    """설정 파일 로드"""
    try:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 필수 설정 확인
        if not all(key in config for key in ['aws', 'snapshot', 'instances']):
            raise ValueError("설정 파일에 필수 설정이 누락되었습니다.")

        # 기본값 설정
        default_retention = config['snapshot'].get('default_retention_months', 3)
        default_profile = config['aws'].get('default_profile', 'default')
        default_region = config['aws'].get('default_region', 'ap-northeast-2')

        # 각 인스턴스에 기본값 적용
        for instance in config['instances']:
            if 'retention_months' not in instance:
                instance['retention_months'] = default_retention
            if 'aws_profile' not in instance:
                instance['aws_profile'] = default_profile
            if 'aws_region' not in instance:
                instance['aws_region'] = default_region

        return config
    except Exception as e:
        print(f"설정 파일 로드 중 오류 발생: {str(e)}")
        raise


# 설정 로드
config = load_config()

# 전역 기본값 설정
DEFAULT_PROFILE = config['aws']['default_profile']
DEFAULT_REGION = config['aws']['default_region']
DEFAULT_RETENTION_MONTHS = config['snapshot']['default_retention_months']

# DB 인스턴스 설정
DB_INSTANCES = config['instances']

# 설정 정보 출력
print("설정 로드 완료:")
print(f"- 기본 AWS 프로필: {DEFAULT_PROFILE}")
print(f"- 기본 AWS 리전: {DEFAULT_REGION}")
print(f"- 기본 스냅샷 보관 기간: {DEFAULT_RETENTION_MONTHS}개월")
print("- DB 인스턴스:")
for instance in DB_INSTANCES:
    print(f"  - {instance['identifier']}:")
    print(f"    유형: {instance['type']}")
    print(f"    프로필: {instance['aws_profile']}")
    print(f"    리전: {instance['aws_region']}")
    print(f"    보관기간: {instance['retention_months']}개월")


def check_sso_credentials(profile_name):
    """SSO 자격 증명 상태 확인"""
    try:
        session = boto3.Session(profile_name=profile_name)
        credentials = session.get_credentials()
        if credentials is None:
            print(f"프로필 '{profile_name}'의 자격 증명을 찾을 수 없습니다.")
            print("AWS SSO 로그인을 다시 수행해주세요: aws sso login --profile", profile_name)
            return False
        return True
    except ProfileNotFound:
        print(f"프로필 '{profile_name}'을 찾을 수 없습니다.")
        print("~/.aws/config 파일에서 프로필 설정을 확인해주세요.")
        return False


def get_boto3_client(profile_name, region_name):
    """환경에 따른 AWS 클라이언트 생성"""
    # EC2 환경인 경우
    if os.path.exists('/sys/hypervisor/uuid'):
        return boto3.client('rds', region_name=region_name)

    # 로컬 개발 환경인 경우
    else:
        # SSO 자격 증명 확인
        if not check_sso_credentials(profile_name):
            raise NoCredentialsError("SSO 자격 증명이 유효하지 않습니다.")

        session = boto3.Session(profile_name=profile_name, region_name=region_name)
        return session.client('rds')


def generate_unique_id(length=8):
    """8자리 랜덤 문자열 생성"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def check_aurora_cluster_state(rds, cluster_identifier):
    """Aurora 클러스터의 상태 확인"""
    try:
        response = rds.describe_db_clusters(
            DBClusterIdentifier=cluster_identifier
        )
        state = response['DBClusters'][0]['Status']
        return state
    except Exception as e:
        print(f"클러스터 상태 확인 중 에러 발생: {str(e)}")
        raise


def create_aurora_snapshot(cluster_identifier):
    """Aurora 클러스터의 수동 스냅샷 생성"""
    try:
        rds = get_boto3_client()

        # 클러스터 상태 확인
        state = check_aurora_cluster_state(rds, cluster_identifier)
        if state != 'available':
            print(f"Aurora 클러스터가 스냅샷을 생성할 수 없는 상태입니다. (현재 상태: {state})")
            print("클러스터가 'available' 상태일 때만 스냅샷을 생성할 수 있습니다.")
            return None

        current_date = datetime.now().strftime('%Y-%m-%d')
        unique_id = generate_unique_id()
        snapshot_identifier = f"{cluster_identifier}-{current_date}-{unique_id}"

        # 클러스터 스냅샷 생성
        response = rds.create_db_cluster_snapshot(
            DBClusterSnapshotIdentifier=snapshot_identifier,
            DBClusterIdentifier=cluster_identifier
        )

        print(f"Aurora 클러스터 스냅샷 생성 시작: {snapshot_identifier}")

        # 스냅샷 생성 완료될 때까지 상태 확인
        print("스냅샷 생성 진행 중...")
        while True:
            response = rds.describe_db_cluster_snapshots(
                DBClusterSnapshotIdentifier=snapshot_identifier
            )
            status = response['DBClusterSnapshots'][0]['Status']
            progress = response['DBClusterSnapshots'][0].get('PercentProgress', 0)

            print(f"진행 상태: {status} ({progress}%)")

            if status == 'available':
                print(f"스냅샷 생성 완료: {snapshot_identifier}")
                break
            elif status == 'failed':
                raise Exception("스냅샷 생성 실패")

            time.sleep(10)

        return response

    except Exception as e:
        print(f"Aurora 스냅샷 생성 중 에러 발생: {str(e)}")
        raise


def check_instance_state(rds, instance_identifier):
    """RDS 인스턴스의 상태 확인"""
    try:
        response = rds.describe_db_instances(
            DBInstanceIdentifier=instance_identifier
        )
        state = response['DBInstances'][0]['DBInstanceStatus']
        return state
    except Exception as e:
        print(f"인스턴스 상태 확인 중 에러 발생: {str(e)}")
        raise


def create_snapshot(instance_identifier):
    """RDS 인스턴스의 수동 스냅샷 생성"""
    try:
        rds = get_boto3_client()

        # 인스턴스 상태 확인
        state = check_instance_state(rds, instance_identifier)
        if state != 'available':
            print(f"RDS 인스턴스가 스냅샷을 생성할 수 없는 상태입니다. (현재 상태: {state})")
            print("인스턴스가 'available' 상태일 때만 스냅샷을 생성할 수 있습니다.")
            return None

        current_date = datetime.now().strftime('%Y-%m-%d')
        unique_id = generate_unique_id()
        snapshot_identifier = f"{instance_identifier}-{current_date}-{unique_id}"

        # 스냅샷 생성 시작
        response = rds.create_db_snapshot(
            DBSnapshotIdentifier=snapshot_identifier,
            DBInstanceIdentifier=instance_identifier
        )

        print(f"스냅샷 생성 시작: {snapshot_identifier}")

        # 스냅샷 생성 완료될 때까지 상태 확인
        print("스냅샷 생성 진행 중...")
        while True:
            response = rds.describe_db_snapshots(
                DBSnapshotIdentifier=snapshot_identifier
            )
            status = response['DBSnapshots'][0]['Status']
            progress = response['DBSnapshots'][0].get('PercentProgress', 0)

            print(f"진행 상태: {status} ({progress}%)")

            if status == 'available':
                print(f"스냅샷 생성 완료: {snapshot_identifier}")
                break
            elif status == 'failed':
                raise Exception("스냅샷 생성 실패")

            time.sleep(10)

        return response

    except Exception as e:
        print(f"스냅샷 생성 중 에러 발생: {str(e)}")
        raise


def is_matching_snapshot_pattern(snapshot_id, instance_identifier):
    """스냅샷 ID가 지정된 패턴과 일치하는지 확인"""
    pattern = f"^{instance_identifier}-\\d{{4}}-\\d{{2}}-\\d{{2}}-[A-Za-z0-9]{{8}}$"
    return bool(re.match(pattern, snapshot_id))


def delete_old_snapshots(instance_identifier, months=3):
    """지정된 패턴의 3개월 이상 된 수동 스냅샷 삭제"""
    try:
        rds = get_boto3_client()

        cutoff_date = datetime.now() - timedelta(days=months * 30)

        print("\n오래된 스냅샷 검색 중...")
        response = rds.describe_db_snapshots(
            DBInstanceIdentifier=instance_identifier,
            SnapshotType='manual'
        )

        # 스냅샷이 없는 경우
        if not response.get('DBSnapshots'):
            print("삭제할 수 있는 스냅샷이 없습니다.")
            return

        # 삭제 대상 스냅샷 식별
        deletion_candidates = []
        for snapshot in response['DBSnapshots']:
            if 'SnapshotCreateTime' not in snapshot:
                continue

            snapshot_id = snapshot['DBSnapshotIdentifier']
            snapshot_create_time = snapshot['SnapshotCreateTime'].replace(tzinfo=None)

            if snapshot_create_time < cutoff_date and is_matching_snapshot_pattern(snapshot_id, instance_identifier):
                deletion_candidates.append((snapshot_id, snapshot_create_time))

        # 삭제 대상 요약
        if not deletion_candidates:
            print(f"{months}개월 이상 된 삭제 대상 스냅샷이 없습니다.")
            return

        print(f"\n총 {len(deletion_candidates)}개의 삭제 대상 스냅샷이 발견되었습니다:")
        for snapshot_id, create_time in deletion_candidates:
            print(f"- {snapshot_id} (생성일: {create_time})")

        # 스냅샷 삭제 실행
        print("\n스냅샷 삭제 진행 중...")
        for snapshot_id, create_time in deletion_candidates:
            try:
                rds.delete_db_snapshot(
                    DBSnapshotIdentifier=snapshot_id
                )
                print(f"스냅샷 삭제 완료: {snapshot_id}")
            except Exception as e:
                print(f"스냅샷 {snapshot_id} 삭제 중 에러 발생: {str(e)}")

        print(f"\n{len(deletion_candidates)}개의 스냅샷 삭제 작업이 완료되었습니다.")

    except Exception as e:
        print(f"스냅샷 삭제 처리 중 에러 발생: {str(e)}")
        raise


def delete_old_aurora_snapshots(cluster_identifier, months=3):
    """오래된 Aurora 클러스터 스냅샷 삭제"""
    try:
        rds = get_boto3_client()

        cutoff_date = datetime.now() - timedelta(days=months * 30)

        print("\n오래된 Aurora 스냅샷 검색 중...")
        response = rds.describe_db_cluster_snapshots(
            DBClusterIdentifier=cluster_identifier,
            SnapshotType='manual'
        )

        if not response.get('DBClusterSnapshots'):
            print("삭제할 수 있는 Aurora 스냅샷이 없습니다.")
            return

        deletion_candidates = []
        for snapshot in response['DBClusterSnapshots']:
            if 'SnapshotCreateTime' not in snapshot:
                continue

            snapshot_id = snapshot['DBClusterSnapshotIdentifier']
            snapshot_create_time = snapshot['SnapshotCreateTime'].replace(tzinfo=None)

            if snapshot_create_time < cutoff_date and is_matching_snapshot_pattern(snapshot_id, cluster_identifier):
                deletion_candidates.append((snapshot_id, snapshot_create_time))

        if not deletion_candidates:
            print(f"{months}개월 이상 된 삭제 대상 Aurora 스냅샷이 없습니다.")
            return

        print(f"\n총 {len(deletion_candidates)}개의 삭제 대상 Aurora 스냅샷이 발견되었습니다:")
        for snapshot_id, create_time in deletion_candidates:
            print(f"- {snapshot_id} (생성일: {create_time})")

        print("\n스냅샷 삭제 진행 중...")
        for snapshot_id, create_time in deletion_candidates:
            try:
                rds.delete_db_cluster_snapshot(
                    DBClusterSnapshotIdentifier=snapshot_id
                )
                print(f"스냅샷 삭제 완료: {snapshot_id}")
            except Exception as e:
                print(f"스냅샷 {snapshot_id} 삭제 중 에러 발생: {str(e)}")

        print(f"\n{len(deletion_candidates)}개의 Aurora 스냅샷 삭제 작업이 완료되었습니다.")

    except Exception as e:
        print(f"Aurora 스냅샷 삭제 처리 중 에러 발생: {str(e)}")
        raise


def process_instance(instance):
    """DB 인스턴스 처리 (RDS 또는 Aurora)"""
    try:
        instance_id = instance['identifier']
        instance_type = instance['type']
        retention_months = instance['retention_months']
        aws_profile = instance['aws_profile']
        aws_region = instance['aws_region']

        print(f"\n[{instance_id}] {instance_type.upper()} 인스턴스 처리 시작...")
        print(f"AWS 프로필: {aws_profile}")
        print(f"AWS 리전: {aws_region}")
        print(f"스냅샷 보관 기간: {retention_months}개월")

        # 인스턴스별 AWS 클라이언트 생성
        rds = get_boto3_client(aws_profile, aws_region)

        if instance_type == 'aurora':
            if check_aurora_cluster_state(rds, instance_id) == 'available':
                snapshot_response = create_aurora_snapshot(instance_id)
                if snapshot_response is not None:
                    delete_old_aurora_snapshots(instance_id, retention_months)
        else:  # rds
            if check_instance_state(rds, instance_id) == 'available':
                snapshot_response = create_snapshot(instance_id)
                if snapshot_response is not None:
                    delete_old_snapshots(instance_id, retention_months)

        print(f"[{instance_id}] 인스턴스 처리 완료")
        return True

    except Exception as e:
        print(f"[{instance_id}] 처리 중 오류 발생: {str(e)}")
        return False


def main():
    print(f"\n처리할 인스턴스 목록:")
    for instance in DB_INSTANCES:
        print(f"- {instance['identifier']} ({instance['type'].upper()})")

    success_count = 0
    failure_count = 0

    for instance in DB_INSTANCES:
        if process_instance(instance):
            success_count += 1
        else:
            failure_count += 1

    print(f"\n처리 완료 요약:")
    print(f"- 전체 인스턴스: {len(DB_INSTANCES)}개")
    print(f"- 성공: {success_count}개")
    print(f"- 실패: {failure_count}개")


if __name__ == "__main__":
    main()