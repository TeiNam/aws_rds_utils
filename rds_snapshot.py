import boto3
import datetime
import random
import string
import re
import os
import sys
import time
from datetime import datetime, timedelta
from botocore.exceptions import ProfileNotFound, NoCredentialsError

# AWS 설정
AWS_PROFILE = 'AdministratorAccess-488659748805'  # AWS SSO 프로필 이름
AWS_REGION = 'ap-northeast-2'  # AWS 리전

# RDS 설정
# RDS 설정
RDS_INSTANCE_IDS = [
    'mgmt-dbre-utilization',
    # 여기에 다른 인스턴스 추가
    # 'instance-2',
    # 'instance-3',
]
SNAPSHOT_RETENTION_MONTHS = 3  # 스냅샷 보관 기간 (월)

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


def get_boto3_client():
    """환경에 따른 AWS 클라이언트 생성"""
    # EC2 환경인 경우
    if os.path.exists('/sys/hypervisor/uuid'):
        return boto3.client('rds', region_name=AWS_REGION)

    # 로컬 개발 환경인 경우
    else:
        # SSO 자격 증명 확인
        if not check_sso_credentials(AWS_PROFILE):
            raise NoCredentialsError("SSO 자격 증명이 유효하지 않습니다.")

        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        return session.client('rds')


def generate_unique_id(length=8):
    """8자리 랜덤 문자열 생성"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


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

            time.sleep(10)  # 10초마다 상태 확인

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


def process_instance(instance_id):
    """단일 RDS 인스턴스에 대한 스냅샷 처리"""
    try:
        print(f"\n[{instance_id}] 인스턴스 처리 시작...")

        # 스냅샷 생성
        snapshot_response = create_snapshot(instance_id)

        # 스냅샷 생성이 성공한 경우에만 삭제 진행
        if snapshot_response is not None:
            # 이전 스냅샷 삭제
            delete_old_snapshots(instance_id, SNAPSHOT_RETENTION_MONTHS)

        print(f"[{instance_id}] 인스턴스 처리 완료")

    except Exception as e:
        print(f"[{instance_id}] 처리 중 오류 발생: {str(e)}")
        # 한 인스턴스의 실패가 다른 인스턴스 처리를 중단하지 않도록 예외를 여기서 처리
        return False

    return True


def main():
    print(f"처리할 인스턴스 목록: {', '.join(RDS_INSTANCE_IDS)}")

    success_count = 0
    failure_count = 0

    for instance_id in RDS_INSTANCE_IDS:
        if process_instance(instance_id):
            success_count += 1
        else:
            failure_count += 1

    # 전체 처리 결과 출력
    total_instances = len(RDS_INSTANCE_IDS)
    print(f"\n처리 완료 요약:")
    print(f"- 전체 인스턴스: {total_instances}개")
    print(f"- 성공: {success_count}개")
    print(f"- 실패: {failure_count}개")


if __name__ == "__main__":
    main()