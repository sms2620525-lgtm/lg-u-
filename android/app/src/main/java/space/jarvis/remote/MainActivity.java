package space.jarvis.remote;

import android.app.Activity;
import android.os.Bundle;
import android.hardware.*;
import android.graphics.Color;
import android.view.WindowManager;
import android.widget.*;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONObject;

public class MainActivity extends Activity implements SensorEventListener {
    SensorManager sensors; Sensor sensor;
    EditText ip, code; TextView status;
    volatile String base="", token="";
    volatile boolean foreground=false;
    ExecutorService worker=Executors.newSingleThreadExecutor();
    AtomicBoolean busy=new AtomicBoolean(false);
    long last=0;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(1);layout.setPadding(40,80,40,40);layout.setBackgroundColor(Color.rgb(6,9,22));
        TextView title=new TextView(this);title.setText("JARVIS\n휴대폰 모션 컨트롤러");title.setTextSize(26);title.setTextColor(Color.rgb(150,235,240));layout.addView(title);
        TextView guide=new TextView(this);guide.setText("맥과 같은 Wi-Fi에 연결하고, 맥 앱에서 ‘휴대폰 연결 코드’를 누르세요.\n휴대폰을 기울이면 맥의 3D 화면이 회전합니다.\n");layout.addView(guide);
        ip=new EditText(this);ip.setSingleLine(true);ip.setHint("맥의 IP (예: 192.168.0.10)");ip.setInputType(17);layout.addView(ip);
        code=new EditText(this);code.setSingleLine(true);code.setHint("6자리 연결 코드");code.setInputType(2);layout.addView(code);
        Button pair=new Button(this);pair.setText("맥에 연결");layout.addView(pair);
        Button stop=new Button(this);stop.setText("전송 중단");layout.addView(stop);
        status=new TextView(this);status.setText("연결 대기 중");status.setPadding(0,25,0,0);layout.addView(status);setContentView(layout);
        sensors=(SensorManager)getSystemService(SENSOR_SERVICE);sensor=sensors.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR);
        if(sensor==null)sensor=sensors.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR);
        if(sensor==null){status.setText("이 휴대폰은 필요한 회전 센서를 제공하지 않습니다.");pair.setEnabled(false);}
        pair.setOnClickListener(v->{
            String address=ip.getText().toString().trim(), pin=code.getText().toString().trim();
            if(!privateIp(address)||!pin.matches("[0-9]{6}")){status.setText("같은 Wi-Fi의 맥 IPv4와 6자리 코드를 입력하세요.");return;}
            if(!busy.compareAndSet(false,true))return;
            token="";base="http://"+address+":8766";status.setText("연결 중…");
            worker.execute(()->{try{JSONObject data=new JSONObject();data.put("pin",pin);String newToken=request("/pair",data,"").getString("token");if(foreground)token=newToken;runOnUiThread(()->status.setText("연결됐어요. 휴대폰을 기울여 보세요."));}catch(Exception e){showError(e);}finally{busy.set(false);}});
        });
        stop.setOnClickListener(v->{token="";status.setText("전송 중단됨. 맥에서도 ‘연결 끊기’를 누를 수 있어요.");});
    }
    boolean privateIp(String ip) {
        if(!ip.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}"))return false;
        String[] parts=ip.split("\\.");int[] p=new int[4];
        for(int i=0;i<4;i++){p[i]=Integer.parseInt(parts[i]);if(p[i]>255)return false;}
        return p[0]==10||(p[0]==192&&p[1]==168)||(p[0]==172&&p[1]>=16&&p[1]<=31);
    }
    JSONObject request(String path,JSONObject body,String auth) throws Exception {
        HttpURLConnection conn=(HttpURLConnection)new URL(base+path).openConnection();
        conn.setConnectTimeout(2500);conn.setReadTimeout(2500);conn.setRequestMethod("POST");conn.setDoOutput(true);conn.setRequestProperty("Content-Type","application/json");
        if(!auth.isEmpty())conn.setRequestProperty("Authorization","Bearer "+auth);
        try {
            try(OutputStream out=conn.getOutputStream()){out.write(body.toString().getBytes(StandardCharsets.UTF_8));}
            int code=conn.getResponseCode();InputStream stream=code==200?conn.getInputStream():conn.getErrorStream();
            String text="";if(stream!=null){try(BufferedReader reader=new BufferedReader(new InputStreamReader(stream,StandardCharsets.UTF_8))){String line;StringBuilder result=new StringBuilder();while((line=reader.readLine())!=null)result.append(line);text=result.toString();}}
            JSONObject result=new JSONObject(text);
            if(code!=200)throw new IOException(result.optString("error","연결 실패"));return result;
        } finally {conn.disconnect();}
    }
    void showError(Exception e){token="";runOnUiThread(()->status.setText("연결 실패: "+e.getMessage()+"\n같은 Wi-Fi와 맥 방화벽 허용 여부를 확인하세요."));}
    @Override public void onSensorChanged(SensorEvent event){
        if(!foreground||token.isEmpty()||event.timestamp-last<50000000||!busy.compareAndSet(false,true))return;
        last=event.timestamp;float[] matrix=new float[9],angles=new float[3];SensorManager.getRotationMatrixFromVector(matrix,event.values);SensorManager.getOrientation(matrix,angles);
        double pitch=Math.toDegrees(angles[1]),roll=Math.toDegrees(angles[2]);String auth=token;
        worker.execute(()->{try{JSONObject data=new JSONObject();data.put("pitch",pitch);data.put("roll",roll);request("/motion",data,auth);}catch(Exception e){showError(e);}finally{busy.set(false);}});
    }
    @Override public void onAccuracyChanged(Sensor sensor,int accuracy){}
    @Override public void onResume(){super.onResume();foreground=true;if(sensor!=null)sensors.registerListener(this,sensor,SensorManager.SENSOR_DELAY_GAME);}
    @Override public void onPause(){foreground=false;sensors.unregisterListener(this);super.onPause();}
    @Override public void onDestroy(){token="";worker.shutdown();super.onDestroy();}
}
