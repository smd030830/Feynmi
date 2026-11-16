import { useCallback, useEffect, useRef, useState } from "react";

type RecognitionResult = {
  readonly isFinal: boolean;
  readonly 0: { readonly transcript: string };
};

type SpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { resultIndex: number; results: ArrayLike<RecognitionResult> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
};

type SpeechWindow = Window & {
  SpeechRecognition?: new () => SpeechRecognition;
  webkitSpeechRecognition?: new () => SpeechRecognition;
};

function recognitionError(error: string) {
  switch (error) {
    case "not-allowed":
    case "service-not-allowed":
      return "음성 입력을 사용하려면 브라우저에서 마이크 접근을 허용해주세요.";
    case "audio-capture":
      return "마이크를 사용할 수 없어요. 마이크 연결과 시스템 설정을 확인해주세요.";
    case "no-speech":
      return "음성이 들리지 않았어요. 음성 입력을 다시 시작해주세요.";
    case "network":
      return "음성 인식 서비스에 연결하지 못했어요. 잠시 후 다시 시도해주세요.";
    case "language-not-supported":
      return "이 브라우저의 음성 인식은 한국어를 지원하지 않아요. 직접 입력해주세요.";
    default:
      return "음성을 인식하지 못했어요. 다시 시도하거나 직접 입력해주세요.";
  }
}

export function useSpeechDictation(sessionId: string, append: (text: string) => void) {
  const recognition = useRef<{ instance: SpeechRecognition; stopping: boolean } | null>(null);
  const [state, setState] = useState<"idle" | "listening" | "stopping">("idle");
  const [message, setMessage] = useState("");

  const abort = useCallback(() => {
    const current = recognition.current;
    if (!current) return;
    const { instance } = current;
    recognition.current = null;
    instance.onresult = instance.onerror = instance.onend = null;
    instance.abort();
    setState("idle");
  }, []);

  useEffect(() => {
    window.addEventListener("pagehide", abort);
    return () => {
      window.removeEventListener("pagehide", abort);
      abort();
    };
  }, [abort, sessionId]);

  function start() {
    if (recognition.current) return;
    const browser = window as SpeechWindow;
    const Recognition = browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
    if (!window.isSecureContext || !Recognition) {
      setMessage("이 환경에서는 음성 입력을 사용할 수 없어요. 설명을 직접 입력해주세요.");
      return;
    }

    let instance: SpeechRecognition;
    try {
      instance = new Recognition();
      instance.lang = "ko-KR";
      instance.continuous = true;
      instance.interimResults = true;
      const current = { instance, stopping: false };
      const interim = new Map<number, string>();
      let receivedSpeech = false;
      let failed = false;

      instance.onresult = ({ resultIndex, results }) => {
        if (recognition.current !== current) return;
        const phrases: string[] = [];
        for (let index = resultIndex; index < results.length; index++) {
          const result = results[index];
          const text = result[0].transcript.trim();
          if (result.isFinal) {
            interim.delete(index);
            if (text) phrases.push(text);
          } else if (text) {
            interim.set(index, text);
          }
        }
        // Some browsers clear the interim results while stopping without delivering a final result.
        if (!current.stopping || phrases.length) {
          for (const index of interim.keys()) {
            if (index >= results.length) interim.delete(index);
          }
        }
        if (phrases.length === 0) return;
        receivedSpeech = true;
        append(phrases.join(" "));
      };
      instance.onerror = ({ error }) => {
        if (recognition.current !== current) return;
        failed = true;
        setMessage(recognitionError(error));
      };
      instance.onend = () => {
        if (recognition.current !== current) return;
        recognition.current = null;
        setState("idle");
        const tail = [...interim.entries()]
          .sort(([a], [b]) => a - b)
          .map(([, text]) => text)
          .join(" ");
        if (tail) {
          append(tail);
          if (!failed) setMessage("마지막 말은 임시 인식 결과로 넣었어요. 보내기 전에 확인해주세요.");
        } else if (!failed && !receivedSpeech) {
          setMessage(recognitionError("no-speech"));
        }
      };

      recognition.current = current;
      setMessage("");
      setState("listening");
      instance.start();
    } catch {
      abort();
      setMessage(recognitionError("unknown"));
    }
  }

  function stop() {
    const current = recognition.current;
    if (!current || current.stopping) return;
    current.stopping = true;
    setState("stopping");
    current.instance.stop();
  }

  return { state, message, start, stop, abort, isActive: () => recognition.current !== null };
}
