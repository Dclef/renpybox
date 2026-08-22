import copy
import threading

from base.Base import Base
from module.Secret.SecretStore import SecretStore
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from module.Engine.TaskRequester import TaskRequester

class APITester(Base):

    @staticmethod
    def _redact_secrets(value: object, keys: list[str]) -> str:
        """从接口测试的所有可见文本中移除已知密钥。"""
        text = str(value or "")
        for key in sorted((key for key in keys if key), key = len, reverse = True):
            text = text.replace(key, "***")
        return text

    def __init__(self) -> None:
        super().__init__()

        # 注册事件
        self.subscribe(Base.Event.PLATFORM_TEST_START, self.platform_test_start)

    # 接口测试开始事件
    def platform_test_start(self, event: str, data: dict) -> None:
        if not Engine.get().try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": Localizer.get().platofrm_tester_running,
            })
        else:
            thread = threading.Thread(
                target = self._platform_test_start_guarded,
                args = (event, data),
            )
            try:
                thread.start()
            except Exception:
                Engine.get().release_status(Engine.Status.TESTING)
                raise

    def _platform_test_start_guarded(self, event: str, data: dict) -> None:
        """保证接口测试异常退出时也会释放全局 AI 任务状态。"""
        try:
            self.platform_test_start_target(event, data)
        finally:
            Engine.get().release_status(Engine.Status.TESTING)

    # 接口测试开始
    def platform_test_start_target(self, event: str, data: dict) -> None:
        # 更新运行状态
        Engine.get().set_status(Engine.Status.TESTING)

        # 加载配置
        config = Config().load()
        platform = config.get_platform(data.get('id'))

        # 测试结果
        failure: list[str] = []
        failure_details: list[str] = []
        success: list[str] = []

        # 构造提示词
        if platform.get('api_format') == Base.APIFormat.SAKURALLM:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，不擅自添加原文中没有的代词。",
                },
                {
                    "role": "user",
                    "content": "将下面的日文文本翻译成中文：魔導具師ダリヤはうつむかない",
                },
            ]
        else:
            messages = [
                {
                    "role": "user",
                    "content": "将下面的日文文本翻译成中文，按输入格式返回结果：{\"0\":\"魔導具師ダリヤはうつむかない\"}",
                },
            ]

        # 重置请求器
        TaskRequester.reset()

        # 开始测试。每轮移除稳定身份并只放一把明文 Key，确保请求器不会
        # 从凭据库轮换到本轮之外的 Key。
        resolved_keys = SecretStore.get().resolve_keys(platform)
        test_keys = resolved_keys or ["no_key_required"]
        for index, key in enumerate(test_keys, start = 1):
            label = f"#{index}"
            test_platform = copy.deepcopy(platform)
            test_platform.pop("id", None)
            test_platform.pop("credential_id", None)
            test_platform.pop("legacy_credential_id", None)
            test_platform["api_key"] = [key]
            requester = TaskRequester(config, test_platform, 0)

            # TaskRequester 会在捕获 SDK 异常时先写全局日志；测试模式下接管
            # 该入口，避免上游异常回显 Key 时绕过本页的结果脱敏。
            def log_request_error(
                message: object,
                error: Exception | None = None,
                *_args,
                **_kwargs,
            ) -> None:
                detail = f"{message}: {error}" if error is not None else message
                self.error(self._redact_secrets(detail, resolved_keys))

            requester.error = log_request_error

            self.print("")
            self.info(f"{Localizer.get().platofrm_tester_key} - {label}")
            self.info(f"{Localizer.get().platofrm_tester_messages}\n{messages}")
            try:
                skip, response_think, response_result, _, _ = requester.request(
                    messages,
                    response_shape = "none",
                )
            except Exception as e:
                failure.append(label)
                failure_details.append(self._redact_secrets(e, resolved_keys))
                self.warning(Localizer.get().log_api_test_fail)
                continue

            # 提取回复内容
            if skip == True:
                failure.append(label)
                if requester.last_error_message:
                    failure_details.append(
                        self._redact_secrets(
                            requester.last_error_message,
                            resolved_keys,
                        )
                    )
                self.warning(Localizer.get().log_api_test_fail)
            elif response_think == "":
                success.append(label)
                response_result = self._redact_secrets(response_result, resolved_keys)
                self.info(
                    f"{Localizer.get().platofrm_tester_response_result}\n{response_result}"
                )
            else:
                success.append(label)
                response_think = self._redact_secrets(response_think, resolved_keys)
                response_result = self._redact_secrets(response_result, resolved_keys)
                self.info(
                    f"{Localizer.get().platofrm_tester_response_think}\n{response_think}"
                )
                self.info(
                    f"{Localizer.get().platofrm_tester_response_result}\n{response_result}"
                )

        # 测试结果
        result_msg = (
            Localizer.get().platofrm_tester_result.replace("{COUNT}", f"{len(test_keys)}")
                                                  .replace("{SUCCESS}", f"{len(success)}")
                                                  .replace("{FAILURE}", f"{len(failure)}")
        )
        if failure_details:
            result_msg = result_msg + "\n" + "\n".join(dict.fromkeys(failure_details))
        self.print("")
        self.info(result_msg)

        # 失败密钥
        if len(failure) > 0:
            self.warning(Localizer.get().platofrm_tester_result_failure + "\n" + "\n".join(failure))

        # 发送完成事件
        self.emit(Base.Event.PLATFORM_TEST_DONE, {
            "result": len(failure) == 0,
            "result_msg": result_msg,
        })

        # 更新运行状态
        Engine.get().set_status(Engine.Status.IDLE)
