import schedule
import time
import logging
from datetime import datetime
from typing import Callable, Dict, Any, Optional, Union, List
import yaml
import os
import importlib
from functools import partial

class Task:
    """작업 클래스"""

    def __init__(
            self,
            name: str,
            func: Callable,
            args: tuple = (),
            kwargs: dict = None,
            enabled: bool = True,
            description: str = ""
    ):
        self.name = name
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.enabled = enabled
        self.description = description
        self.last_run = None
        self.next_run = None

    def run(self):
        """작업 실행"""
        if not self.enabled:
            logging.info(f"작업 {self.name}이 비활성화되어 있습니다.")
            return

        try:
            logging.info(f"작업 {self.name} 실행 시작")
            self.last_run = datetime.now()
            self.func(*self.args, **self.kwargs)
            logging.info(f"작업 {self.name} 실행 완료")
        except Exception as e:
            logging.error(f"작업 {self.name} 실행 중 오류 발생: {str(e)}", exc_info=True)


class TaskScheduler:
    """작업 스케줄러"""

    def __init__(self, config_path: str = 'scheduler_config.yml'):
        # 로깅 설정
        self.setup_logging()

        self.tasks = {}
        self.config_path = config_path
        self.config = self.load_config()

        # 설정 파일에서 작업 자동 등록
        self.register_tasks_from_config()

    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('scheduler.log')
            ]
        )
        self.logger = logging.getLogger('TaskScheduler')

    def load_config(self) -> dict:
        """설정 파일 로드"""
        try:
            if not os.path.exists(self.config_path):
                self.logger.warning(f"설정 파일이 없습니다. 기본 설정 파일을 생성합니다: {self.config_path}")
                self._create_default_config()

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self.logger.info(f"설정 파일 로드 완료: {self.config_path}")
                return config

        except Exception as e:
            self.logger.error(f"설정 파일 로드 중 오류 발생: {str(e)}")
            raise

    def _create_default_config(self):
        """기본 설정 파일 생성"""
        default_config = {
            'tasks': {
                'rds_backup': {
                    'module': 'rds_snapshot',
                    'function': 'process_instance',
                    'args': [],
                    'kwargs': {},
                    'schedule': {
                        'type': 'daily',
                        'at': '02:00'
                    },
                    'enabled': True,
                    'description': 'RDS 백업 작업'
                }
            },
            'logging': {
                'level': 'INFO',
                'file': 'scheduler.log'
            }
        }

        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

    def register_tasks_from_config(self):
        """설정 파일에서 작업 등록"""
        if not self.config or 'tasks' not in self.config:
            self.logger.warning("설정 파일에 작업이 정의되어 있지 않습니다.")
            return

        for task_name, task_config in self.config['tasks'].items():
            try:
                if not task_config.get('enabled', True):
                    self.logger.info(f"작업 {task_name}이 비활성화되어 있어 등록하지 않습니다.")
                    continue

                # 모듈과 함수 임포트
                module_name = task_config.get('module')
                function_name = task_config.get('function')

                if not module_name or not function_name:
                    self.logger.error(f"작업 {task_name}의 모듈 또는 함수가 지정되지 않았습니다.")
                    continue

                try:
                    module = importlib.import_module(module_name)
                    func = getattr(module, function_name)
                except Exception as e:
                    self.logger.error(f"모듈 {module_name}의 함수 {function_name} 임포트 중 오류: {str(e)}")
                    continue

                # 스케줄 정보 가져오기
                schedule_config = task_config.get('schedule', {})
                schedule_type = schedule_config.get('type')
                schedule_time = schedule_config.get('at') if schedule_type != 'interval' else schedule_config.get(
                    'minutes')

                if not schedule_type or schedule_time is None:
                    self.logger.error(f"작업 {task_name}의 스케줄 설정이 잘못되었습니다.")
                    continue

                # 작업 등록
                self.add_task(
                    name=task_name,
                    func=func,
                    schedule_type=schedule_type,
                    schedule_time=schedule_time,
                    args=task_config.get('args', []),
                    kwargs=task_config.get('kwargs', {}),
                    enabled=task_config.get('enabled', True),
                    description=task_config.get('description', '')
                )

            except Exception as e:
                self.logger.error(f"작업 {task_name} 등록 중 오류 발생: {str(e)}")

    def add_task(
            self,
            name: str,
            func: Callable,
            schedule_type: str,
            schedule_time: Union[str, int],
            args: tuple = (),
            kwargs: dict = None,
            enabled: bool = True,
            description: str = ""
    ):
        """작업 추가"""
        task = Task(name, func, args, kwargs, enabled, description)
        self.tasks[name] = task

        schedule_func = self._get_schedule_function(schedule_type, schedule_time)
        if schedule_func:
            schedule_func.do(task.run)
            self.logger.info(f"작업 {name} 등록 완료 (스케줄: {schedule_type} {schedule_time})")
        else:
            self.logger.error(f"작업 {name} 등록 실패: 잘못된 스케줄 설정")

    def _get_schedule_function(self, schedule_type: str, schedule_time: Union[str, int]):
        """스케줄 타입에 따른 schedule 함수 반환"""
        try:
            if schedule_type == 'interval':
                return schedule.every(int(schedule_time)).minutes
            elif schedule_type == 'daily':
                return schedule.every().day.at(schedule_time)
            elif schedule_type == 'weekly':
                day, time = schedule_time.split()
                return getattr(schedule.every(), day.lower()).at(time)
            elif schedule_type == 'monthly':
                day, time = schedule_time.split()
                return schedule.every().month.at(time)
            else:
                self.logger.error(f"지원하지 않는 스케줄 타입: {schedule_type}")
                return None
        except Exception as e:
            self.logger.error(f"스케줄 함수 생성 중 오류: {str(e)}")
            return None

    def remove_task(self, name: str):
        """작업 제거"""
        if name in self.tasks:
            schedule.clear(name)
            del self.tasks[name]
            self.logger.info(f"작업 {name} 제거됨")

    def enable_task(self, name: str):
        """작업 활성화"""
        if name in self.tasks:
            self.tasks[name].enabled = True
            self.logger.info(f"작업 {name} 활성화됨")

    def disable_task(self, name: str):
        """작업 비활성화"""
        if name in self.tasks:
            self.tasks[name].enabled = False
            self.logger.info(f"작업 {name} 비활성화됨")

    def list_tasks(self) -> List[Dict[str, Any]]:
        """등록된 작업 목록 반환"""
        return [{
            'name': name,
            'enabled': task.enabled,
            'description': task.description,
            'last_run': task.last_run,
            'next_run': task.next_run
        } for name, task in self.tasks.items()]

    def run(self):
        """스케줄러 실행"""
        if not self.tasks:
            self.logger.warning("등록된 작업이 없습니다.")
            return

        self.logger.info("스케줄러 시작")
        self.logger.info("등록된 작업 목록:")
        for task_info in self.list_tasks():
            self.logger.info(f"- {task_info['name']} (활성화: {task_info['enabled']})")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 체크
        except KeyboardInterrupt:
            self.logger.info("스케줄러 종료")
        except Exception as e:
            self.logger.error(f"스케줄러 실행 중 오류 발생: {str(e)}")
            raise


if __name__ == "__main__":
    # 스케줄러 시작
    scheduler = TaskScheduler()
    scheduler.run()